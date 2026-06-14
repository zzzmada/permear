"""Systems Consolidation — the weekly compile, in-process (v8.10).

Replaces the shell chain cycles.yaml systems automation +
build_systems_prompt.py + correlate_events.py (subprocess) + systems_compile.py.

Flow (unchanged from production):
  deterministic co-occurrence over event_log 7d (correlate module, ≥3
  DISTINCT days) → pairs injected as a structured block into the PT prompt
  together with the week's consolidated memories + interactions → ONE
  ai_task call (data provider, fallback choreography) → suggestions/pending
  written to memory_items source='systems' (metadata.insight_type) →
  engagement-based priority learning → PT summary via Telegram.

The system SUGGESTS; it never declares an automation. Residents are read
from the HA person registry (v9.0.1 — guidelines.json is gone); the
component never writes household data. Removals are deferred to tier decay. When both
providers fail, the LLM block is skipped but the deterministic part
(engagement learning + summary) still runs — same as production.

forget_old_items (shell step 1) is a deliberate no-op since v8.7 (rule #47)
and is not ported. Scheduling: cycles.systems_time, Sundays, LOCAL time.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util.yaml import load_yaml

from .config import PermearConfig, parse_hhmm
from .const import (
    AGENT_AUTOMATIONS_RELATIVE_PATH,
    DEFAULT_SYSTEMS_TIME,
    EVENT_LOG_CORRELATION_DAYS,
)
from .correlate import compute_pairs
from .household import get_residents
from .llm import AiTaskClient
from .notify import async_send_telegram
from .storage import PermearStorage

_LOGGER = logging.getLogger(__name__)

SYSTEMS_WEEKDAY = 6  # Sunday (datetime.weekday())

# Pendencias mentioning the framework itself are filtered out (PERMEAR errors
# are never household pending items).
META_KEYWORDS = (
    "weekly_compile", "compilacao_semanal", "byte offset",
    "cant parse entities", "parse entities", "compile.py",
    "weekly_compile_error", "process_log_event",
)

DIRETRIZES_RESUMO = """DIRETRIZES (resumo — regras completas validadas pelo Python pós-resposta):
- residents: moradores lidos do registro de pessoas do Home Assistant (somente leitura).
- memory_items source='systems': insights do sistema (suggestions/sugestoes e pending/pendencias). Decay nativo do banco substitui poda manual.
- NUNCA duplicar info entre arquivos. Antes de adicionar, verificar se ja existe."""

INSIGHTS_STRUCTURE = {
    "novas_pendencias": {
        "description": "Household pending items to register",
        "required": False,
        "selector": {"text": {"multiple": True}},
    },
    "remover_pendencias": {
        "description": "Pending items to remove (exact text)",
        "required": False,
        "selector": {"text": {"multiple": True}},
    },
    "novas_sugestoes": {
        "description": "Automation suggestions",
        "required": False,
        "selector": {"text": {"multiple": True}},
    },
}


def _is_meta_pendency(text: str) -> bool:
    return bool(text) and any(kw in text.lower() for kw in META_KEYWORDS)


class PermearSystems:
    """Schedules and runs the weekly Systems Consolidation."""

    def __init__(
        self,
        hass: HomeAssistant,
        storage: PermearStorage,
        config: PermearConfig,
        llm: AiTaskClient,
    ) -> None:
        self._hass = hass
        self._storage = storage
        self._config = config
        self._llm = llm
        self._unsub = None
        self._task: asyncio.Task | None = None
        self._running = False

    @callback
    def start(self) -> None:
        hour, minute = parse_hhmm(self._config.systems_time, DEFAULT_SYSTEMS_TIME)
        self._unsub = async_track_time_change(
            self._hass, self._on_time, hour=hour, minute=minute, second=0
        )
        _LOGGER.info(
            "Systems Consolidation scheduled Sundays at %02d:%02d local",
            hour, minute,
        )

    @callback
    def stop(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _on_time(self, _now) -> None:
        if datetime.now().weekday() != SYSTEMS_WEEKDAY:
            return
        if self._running:  # mode: single
            _LOGGER.warning("Systems Consolidation still running — skipping")
            return
        self._running = True
        self._task = asyncio.current_task()
        try:
            await self.async_run()
        except Exception:  # noqa: BLE001 — the cycle must never crash HA
            _LOGGER.exception("Systems Consolidation failed")
        finally:
            self._running = False
            self._task = None

    # ------------------------------------------------------------------
    # The cycle
    # ------------------------------------------------------------------

    async def async_run(self) -> dict:
        # Deterministic part first: co-occurrence over event_log (no LLM)
        log_rows = await self._storage.async_event_log_range(
            EVENT_LOG_CORRELATION_DAYS
        )
        # CPU-bound over 7 days of event_log — keep it off the loop (Pi 2GB)
        pairs = await self._hass.async_add_executor_job(compute_pairs, log_rows)

        insights = await self._storage.async_system_insights()
        memorias = await self._storage.async_recent_memories(days=7, source="daily")
        interacoes = await self._storage.async_recent_interactions(days=7)
        # Residents come from the HA person registry (loop-safe, in-memory)
        residents = get_residents(self._hass)
        agent_autos = await self._hass.async_add_executor_job(
            self._load_prompt_files
        )

        prompt = self._build_prompt(
            insights, residents, agent_autos, memorias, interacoes, pairs
        )
        data = await self._llm.async_generate(
            "Systems Consolidation - insights", prompt, INSIGHTS_STRUCTURE
        )
        if data is None:
            _LOGGER.warning("Systems insights failed on both providers — "
                            "writing nothing; deterministic part continues")

        applied = await self._compile(data or {})
        summary = self._format_summary(applied, len(agent_autos))
        await async_send_telegram(self._hass, summary)
        _LOGGER.info("Systems Consolidation done: %s", applied)
        return applied

    def _load_prompt_files(self) -> list:
        agent_autos = []
        path = self._hass.config.path(AGENT_AUTOMATIONS_RELATIVE_PATH)
        try:
            raw = load_yaml(path)
            if isinstance(raw, list):
                agent_autos = raw
        except (FileNotFoundError, OSError):
            pass
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("Cannot parse %s: %s", path, exc)
        return agent_autos

    # ------------------------------------------------------------------
    # Prompt (PT body — ports build_systems_prompt.py; the FORMATO JSON
    # trailer was replaced by the ai_task structure)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(
        insights, residents, agent_autos, memorias, interacoes, pairs
    ) -> str:
        autos_txt = (
            json.dumps(
                [{"alias": a.get("alias", "?"), "id": a.get("id", "?")}
                 for a in agent_autos],
                ensure_ascii=False,
            )
            if agent_autos else "[]"
        )

        semana_txt = ""
        if memorias:
            semana_txt += "\nMemorias extraidas da semana (banco de memoria):\n"
            for m in memorias:
                semana_txt += f"  - {m}\n"
        if interacoes:
            semana_txt += "\nInteracoes da semana (Telegram/voz, banco de memoria):\n"
            for i in interacoes:
                semana_txt += f"  [{i['canal']}] {i['content']}\n"
        if not semana_txt.strip():
            semana_txt = "  (sem dados registrados esta semana)"

        if pairs:
            correl_txt = ("\nPARES CO-OCORRENTES (>=3 dias) — eventos que ocorrem "
                          "juntos com frequencia:\n")
            for p in pairs:
                correl_txt += (f"  {p['a']} ↔ {p['b']}: {p['dias']} dias, "
                               f"{p['ocorrencias']} ocorrencias\n")
            correl_txt += (
                "INSTRUCAO: destes pares, proponha AUTOMACAO SOMENTE quando "
                "sugerirem uma rotina domestica plausivel. Ignore pares "
                "espurios ou coincidenciais.\n"
            )
        else:
            correl_txt = ("\n(nenhum par co-ocorrente com >=3 dias detectado "
                          "esta semana)\n")

        return f"""COMPILACAO SEMANAL — Analise a semana e proponha edicoes aos arquivos perenes.

{DIRETRIZES_RESUMO}

ESTADO ATUAL DOS ARQUIVOS PERENES:

|--- insights do sistema (memory_items source='systems') ---
{json.dumps(insights, ensure_ascii=False, indent=2)}

|--- residents (registro de pessoas do Home Assistant) ---
{json.dumps(residents, ensure_ascii=False, indent=2)}

AUTOMACOES ATUAIS DO AGENTE (permear_agent.yaml):
{autos_txt}

DADOS DA SEMANA (banco de memoria — memorias consolidadas + interacoes):
{semana_txt}
{correl_txt}
INSTRUCOES (relevancia > completude):

Analise os 7 dias e identifique APENAS as mudancas mais relevantes da semana.
Maximo 3 novas_sugestoes (apenas se realmente acionaveis) e novas_pendencias (apenas itens acionaveis da casa, nunca erros do framework).
Pendencias: SOMENTE itens da casa (temperatura, sensores, dispositivos, eletrodomesticos). NUNCA inclua erros do proprio framework PERMEAR (compilacao_semanal, weekly_compile, byte offset, parse entities, etc).
Verificar se ja existe na lista atual antes de adicionar.
Se nao houver mudancas relevantes em uma categoria, retornar lista vazia."""

    # ------------------------------------------------------------------
    # Compile (ports systems_compile.py — insights → DB, never guidelines)
    # ------------------------------------------------------------------

    async def _compile(self, changes: dict) -> dict:
        applied = {
            "pending_added": 0, "pending_removed": 0,
            "new_suggestions_list": [],
        }

        for s in changes.get("novas_sugestoes") or []:
            if not s:
                continue
            await self._storage.async_add_or_reinforce(
                str(s), kind="observation", source="systems",
                metadata={"insight_type": "suggestion"},
            )
            applied["new_suggestions_list"].append(str(s))

        for p in changes.get("novas_pendencias") or []:
            if not p or _is_meta_pendency(str(p)):
                continue
            await self._storage.async_add_or_reinforce(
                str(p), kind="observation", source="systems",
                metadata={"insight_type": "pending"},
            )
            applied["pending_added"] += 1

        # remover_pendencias: deferred to tier decay — count only
        applied["pending_removed"] = len(changes.get("remover_pendencias") or [])

        applied["priority_changes"] = (
            await self._storage.async_adjust_priorities_by_engagement()
        )
        return applied

    @staticmethod
    def _format_summary(applied, agent_autos_count) -> str:
        """Telegram summary — user-facing, stays PT (i18n)."""
        lines = ["Resumo da semana:"]

        ns = applied.get("new_suggestions_list", [])
        if ns:
            sample = ns[0][:80] if ns[0] else ""
            lines.append(
                f"- Sugestoes novas: {len(ns)} ({sample}{'...' if len(ns) > 1 else ''})"
            )

        pa, pr = applied.get("pending_added", 0), applied.get("pending_removed", 0)
        if pa or pr:
            lines.append(f"- Pendencias: +{pa} -{pr}")

        prio_changes = applied.get("priority_changes", [])
        if prio_changes:
            lines.append(
                f"- Prioridades ajustadas por engajamento: {len(prio_changes)}"
            )
            for c in prio_changes:
                pct = int(c["rate"] * 100)
                lines.append(
                    f"  - {c['entity']}: {c['from']}->{c['to']} "
                    f"(reagiu {pct}%, {c['alerts']} alertas)"
                )
        else:
            lines.append("- Prioridades: nenhum ajuste.")

        if len(lines) == 2 and lines[-1] == "- Prioridades: nenhum ajuste.":
            lines.insert(1, "- Nenhuma mudanca relevante esta semana.")

        lines.append(f"- Automacoes do agente: {agent_autos_count} ativas")
        return "\n".join(lines)
