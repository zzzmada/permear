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
import re
from datetime import datetime

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change

from .ai_client import AiTaskClient
from .config import PermearConfig, parse_hhmm
from .const import (
    DEFAULT_SYSTEMS_TIME,
    EVENT_LOG_CORRELATION_DAYS,
    MONITORED_ENTITIES_RELATIVE_PATH,
    STANDING_RULES_RELATIVE_PATH,
    SUGGESTION_ACTIONS,
)
from .correlate import compute_pairs
from .household import get_residents
from .notify import async_defer_message
from .storage import PermearStorage, load_json

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

# v9.16 — a suggestion's subject: closed tags at the end of the sentence, in the
# [entity:...] idiom of the Sleep extraction. The output stays a list of texts.
_TRIGGER_TAG = re.compile(r"\[gatilho:([^\]]*)\]")
_SUBJECT_TAGS = re.compile(r"\[alvo:([^\]]*)\]\s*\[acao:([^\]]*)\]")

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


def parse_suggestion(raw: str, valid_ids) -> tuple:
    """(text, subject). subject = 'action|entity,entity|trigger', the identity of the
    suggestion and of its refusal: never its wording, which changes weekly and
    which bm25 matches by the verb (rule #29). None when the tags are missing or
    name something that does not exist. PURE."""
    valid_ids = set(valid_ids)
    match = _SUBJECT_TAGS.search(raw)
    text = " ".join(_TRIGGER_TAG.sub(" ", _SUBJECT_TAGS.sub(" ", raw)).split())
    if not text or not match or len(_SUBJECT_TAGS.findall(raw)) != 1:
        return text, None
    entities = sorted({e.strip() for e in match.group(1).split(",") if e.strip()})
    action = match.group(2).strip().lower()
    if (action not in SUGGESTION_ACTIONS or not entities
            or not set(entities) <= set(valid_ids)):
        return text, None
    tags = _TRIGGER_TAG.findall(raw)
    if len(tags) != 1:
        return text, None
    parts = [p.strip() for p in tags[0].split(":")]
    coordinate = None
    if parts[0] == "time" and len(parts) in (3, 4):
        values = parts[1:]
        if all(re.fullmatch(r"\d{2}", value) for value in values):
            hour, minute = map(int, values[:2])
            second = int(values[2]) if len(values) == 3 else 0
            if hour < 24 and minute < 60 and second < 60:
                coordinate = f"time:{hour:02d}:{minute:02d}:{second:02d}"
    elif parts[0] == "state" and len(parts) == 3:
        entity_id, value = parts[1:]
        if entity_id in valid_ids and re.fullmatch(r"[\w.-]+", value):
            coordinate = f"state:{entity_id}:{value}"
    if coordinate is None:
        return text, None
    return text, f"{action}|{','.join(entities)}|{coordinate}"


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

        entidades = await self._hass.async_add_executor_job(self._monitored_ids)
        prompt = self._build_prompt(
            insights, residents, agent_autos, memorias, interacoes, pairs, entidades
        )
        data = await self._llm.async_generate(
            "Systems Consolidation - insights", prompt, INSIGHTS_STRUCTURE
        )
        if data is None:
            _LOGGER.warning("Systems insights failed on both providers — "
                            "writing nothing; deterministic part continues")

        applied = await self._compile(data or {}, entidades)
        # _compile has ALREADY persisted (insights in the DB, engagement deltas
        # in monitored_entities.json). A failure while merely WORDING the report
        # must never swallow the week's work: on 2026-08-16 a KeyError in the
        # summary killed the cycle after everything was written, and the
        # resident got no weekly message at all (v9.7.1).
        try:
            summary = self._format_summary(applied, len(agent_autos))
        except Exception:  # noqa: BLE001 — formatting is never worth the cycle
            _LOGGER.exception("Systems summary formatting failed — "
                              "delivering the raw result instead")
            summary = f"Resumo da semana (formato degradado): {applied}"
        # v9.2.2 — defer delivery to 08:00 (the weekly cycle still runs now).
        await async_defer_message(self._hass, "systems", summary)
        _LOGGER.info("Systems Consolidation done: %s", applied)
        return applied

    def _monitored_ids(self) -> list:
        data = load_json(
            self._hass.config.path(MONITORED_ENTITIES_RELATIVE_PATH),
            {"entities": []},
        )
        return sorted(
            e["entity_id"] for e in data.get("entities", [])
            if isinstance(e, dict) and e.get("entity_id") and e.get("monitor")
        )

    def _load_prompt_files(self) -> list:
        rules = load_json(self._hass.config.path(STANDING_RULES_RELATIVE_PATH), [])
        return rules if isinstance(rules, list) else []

    # ------------------------------------------------------------------
    # Prompt (PT body — ports build_systems_prompt.py; the FORMATO JSON
    # trailer was replaced by the ai_task structure)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(
        insights, residents, agent_autos, memorias, interacoes, pairs,
        entidades=(),
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
                "INSTRUCAO: destes pares, proponha AVISO SOMENTE quando "
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

AVISOS PERMANENTES ATUAIS:
{autos_txt}

DADOS DA SEMANA (banco de memoria — memorias consolidadas + interacoes):
{semana_txt}
{correl_txt}
INSTRUCOES (relevancia > completude):

Analise os 7 dias e identifique APENAS as mudancas mais relevantes da semana.
Maximo 3 novas_sugestoes (apenas se realmente acionaveis) e novas_pendencias (apenas itens acionaveis da casa, nunca erros do framework).
Cada sugestao e um AVISO ao morador: voce nao aciona, liga, desliga, abre, fecha, ajusta nem agrupa nada, entao nunca sugira isso.
Cada sugestao nomeia o GATILHO (um horario, ou uma entidade mudando de estado) e o que sera avisado: "Avisar sobre a porta" nao e sugestao; "Avisar as 22h se a porta estiver aberta" e. O morador aceita ou recusa exatamente o que estiver escrito.
Cada sugestao termina com as etiquetas [alvo:<entity_id>] [acao:<tipo>] [gatilho:time:HH:MM:SS] para horario ou [gatilho:state:<entity_id>:<estado>] para mudanca de estado, com os entity_id do alvo separados por virgula. <tipo> e um de: {', '.join(sorted(SUGGESTION_ACTIONS))}. Ex: "Avisar as 22h se a porta estiver aberta [alvo:binary_sensor.door_example] [acao:notificar] [gatilho:time:22:00:00]". Sem essas etiquetas a sugestao e descartada.
Entidades da casa: {json.dumps(list(entidades), ensure_ascii=False)}
Pendencias: SOMENTE itens da casa (temperatura, sensores, dispositivos, eletrodomesticos). NUNCA inclua erros do proprio framework PERMEAR (compilacao_semanal, weekly_compile, byte offset, parse entities, etc).
Verificar se ja existe na lista atual antes de adicionar.
Se nao houver mudancas relevantes em uma categoria, retornar lista vazia."""

    # ------------------------------------------------------------------
    # Compile (ports systems_compile.py — insights → DB, never guidelines)
    # ------------------------------------------------------------------

    async def _compile(self, changes: dict, entidades=()) -> dict:
        applied = {
            "pending_added": 0, "pending_removed": 0,
            "new_suggestions_list": [], "suggestions_blocked": 0,
            "suggestions_dropped": 0,
        }

        ids = []
        for s in changes.get("novas_sugestoes") or []:
            if not s:
                continue
            text, subject = parse_suggestion(str(s), entidades)
            # v9.18 — no subject means it is not something a standing rule can
            # do, or names what does not exist. Refused here, not at the yes:
            # what the code would refuse never reaches the resident.
            if not subject:
                applied["suggestions_dropped"] += 1
                _LOGGER.info("Suggestion dropped, not a valid notice: %r", text)
                continue
            if await self._storage.async_suggestion_blocked(subject):
                applied["suggestions_blocked"] += 1
                continue
            item_id, _, _ = await self._storage.async_add_or_reinforce(
                text, kind="observation", source="systems",
                key=f"suggestion:{subject}",
                metadata={"insight_type": "suggestion", "subject": subject},
            )
            ids.append(item_id)
        # The row speaks, not this week's sentence: a reinforce keeps the words
        # the subject was born with, and those are what an answer refers to.
        applied["new_suggestions_list"] = [
            p for p in await self._storage.async_pending_suggestions()
            if p["id"] in ids
        ]

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

        # v9.16 — every suggestion in full: this is what a yes consents to. The
        # #id is how the Telegram handler knows what was offered.
        ns = applied.get("new_suggestions_list", [])
        for s in ns:
            lines.append(f"- Sugestao #{s['id']}: {s['content']}")
        if ns:
            lines.append("  Responda: aceito N ou recuso N.")

        pa, pr = applied.get("pending_added", 0), applied.get("pending_removed", 0)
        if pa or pr:
            lines.append(f"- Pendencias: +{pa} -{pr}")

        # v9.7 moved engagement from writing `priority` absolutely to moving a
        # bounded DELTA over the memory floor, and renamed the reported keys
        # from/to → delta_from/delta_to. This reader was not updated and raised
        # KeyError: 'from' on 2026-08-16. The wording follows the rename too: an
        # engagement adjustment is no longer a priority value, it is the delta
        # the nightly tiers→priority loop applies on top of the memory floor.
        prio_changes = applied.get("priority_changes") or []
        if prio_changes:
            lines.append(
                f"- Atencao ajustada por engajamento: {len(prio_changes)}"
            )
            for c in prio_changes:
                # v9.7.2 — the rate is gone; the reason is what the reader
                # needs. "ignorado" = many alerts and not one reaction in the
                # evidence window; "sem evidencia" = the demotion expired.
                motivo = ("ignorado" if c.get("reason") == "ignored"
                          else "sem evidencia")
                lines.append(
                    f"  - {c.get('entity', '?')}: ajuste "
                    f"{c.get('delta_from', 0)}->{c.get('delta_to', 0)} "
                    f"({motivo}, {c.get('alerts', 0)} alertas, "
                    f"{c.get('reacted', 0)} reacoes)"
                )
        else:
            lines.append("- Atencao: nenhum ajuste.")

        if len(lines) == 2 and lines[-1] == "- Atencao: nenhum ajuste.":
            lines.insert(1, "- Nenhuma mudanca relevante esta semana.")

        lines.append(f"- Avisos permanentes: {agent_autos_count} ativos")
        return "\n".join(lines)
