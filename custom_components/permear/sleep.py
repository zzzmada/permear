"""Sleep Consolidation — nightly memory extraction, in-process (v8.10).

Replaces the shell chain cycles.yaml sleep automation + build_sleep_prompt.py
+ apply_sleep_memories.py + sleep_simple.py + run_memory_maintenance.py.

Flow (unchanged from production):
  build prompt from today's DB context → empty day suppresses EVERYTHING
  (no LLM call, no message, no maintenance) → ONE ai_task call for the
  briefing (data provider, fallback choreography) → deliver PT briefing →
  ONE ai_task call extracting up to 5 memories → write to Organic Memory
  with canonical key validated against monitored_entities.json (invalid or
  multi-entity → keyless, FTS fallback) → tier maintenance + tiers→priority
  loop with bidirectional decay.

When both providers fail the briefing, the deterministic fallback sends a
short PT summary and persists NOTHING (sleep_simple contract) — honest, no
degraded LLM mode. Scheduling: cycles.sleep_time (permear.yaml), LOCAL time.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util.yaml import load_yaml

from .config import PermearConfig, parse_hhmm
from .const import (
    AGENT_AUTOMATIONS_RELATIVE_PATH,
    DAYS_PT,
    DEFAULT_SLEEP_TIME,
    EVENT_SLEEP_COMPLETE,
    MONITORED_ENTITIES_RELATIVE_PATH,
    SLEEP_EXTRACTION_DELAY_SECONDS,
    SLEEP_EXTRACTION_MAX_EVENTS,
)
from .llm import AiTaskClient, circuit_health_summary
from .notify import async_defer_message, async_set_last_message
from .storage import PermearStorage, load_json

_LOGGER = logging.getLogger(__name__)

ENTITY_TAG = re.compile(r"\[entity:([^\]]+)\]\s*$")

BRIEFING_STRUCTURE = {
    "briefing": {
        "description": "Full briefing text, max 120 words, PT-BR, no markdown.",
        "required": True,
        "selector": {"text": {"multiline": True}},
    }
}

MEMORIES_STRUCTURE = {
    "memorias": {
        "description": "List of relevant memories (short phrases, PT-BR)",
        "required": True,
        "selector": {"text": {"multiple": True}},
    },
    # v9.0.2 — restriction intents from natural conversation. The LLM only
    # TRANSLATES speech→intent here; the deterministic ARAS decides later.
    "restricoes": {
        "description": (
            "Subjects the resident asked NOT to be notified about, or said "
            "are irrelevant (short PT-BR phrase per subject). Empty if none."
        ),
        "required": False,
        "selector": {"text": {"multiple": True}},
    },
}


class PermearSleep:
    """Schedules and runs the nightly Sleep Consolidation."""

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
        hour, minute = parse_hhmm(self._config.sleep_time, DEFAULT_SLEEP_TIME)
        self._unsub = async_track_time_change(
            self._hass, self._on_time, hour=hour, minute=minute, second=0
        )
        _LOGGER.info("Sleep Consolidation scheduled at %02d:%02d local", hour, minute)

    @callback
    def stop(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _on_time(self, _now) -> None:
        if self._running:  # mode: single
            _LOGGER.warning("Sleep Consolidation still running — skipping")
            return
        self._running = True
        self._task = asyncio.current_task()
        try:
            await self.async_run()
        except Exception:  # noqa: BLE001 — the cycle must never crash HA
            _LOGGER.exception("Sleep Consolidation failed")
        finally:
            self._running = False
            self._task = None

    # ------------------------------------------------------------------
    # The cycle
    # ------------------------------------------------------------------

    async def async_run(self) -> dict:
        daily = await self._storage.async_daily_summary()
        insights = await self._storage.async_system_insights()
        eventos = daily["eventos"][-10:]
        interacoes = daily["interacoes"]
        pendencias = [i["content"] for i in insights["pending"]]
        sugestoes = [i["content"] for i in insights["suggestions"]]

        # Empty-day suppression: nothing to synthesize, nothing runs (v8.3)
        if not eventos and not interacoes and not pendencias and not sugestoes:
            _LOGGER.info("Sleep Consolidation suppressed — empty day")
            return {"suppressed": True}

        agent_autos, health_line = await self._hass.async_add_executor_job(
            self._load_prompt_files
        )
        prompt = self._build_briefing_prompt(
            eventos, len(interacoes), pendencias, sugestoes, agent_autos, health_line
        )

        data = await self._llm.async_generate(
            "Sleep Consolidation", prompt, BRIEFING_STRUCTURE
        )
        briefing = str((data or {}).get("briefing") or "").strip()

        if len(briefing) <= 5:
            # sleep_simple contract: short deterministic PT summary, NO persist
            fallback = self._simple_briefing(len(daily["eventos"]),
                                             len(interacoes), pendencias)
            # v9.2.2 — defer delivery to 08:00 (the cycle still runs at ~23:30).
            await async_defer_message(self._hass, "sleep", fallback)
            _LOGGER.warning("Sleep briefing failed on both providers — "
                            "simple fallback deferred, nothing persisted")
            return {"suppressed": False, "briefing": False}

        # v9.2.2 — persist the briefing for the 08:00 drain instead of sending now.
        await async_defer_message(self._hass, "sleep", briefing)
        await async_set_last_message(self._hass, briefing)

        # Brief pause between the two LLM calls (provider courtesy, as shell)
        await asyncio.sleep(SLEEP_EXTRACTION_DELAY_SECONDS)

        extraction = await self._llm.async_generate(
            "Memory extraction",
            self._build_extraction_prompt(
                daily["eventos"][-SLEEP_EXTRACTION_MAX_EVENTS:], interacoes
            ),
            MEMORIES_STRUCTURE,
        )
        memorias = (extraction or {}).get("memorias") or []
        if isinstance(memorias, str):
            memorias = [memorias]
        applied = await self._apply_memories(memorias)

        restricoes = (extraction or {}).get("restricoes") or []
        if isinstance(restricoes, str):
            restricoes = [restricoes]
        restrictions_applied = await self._apply_restrictions(restricoes)

        maintenance = await self._storage.async_run_maintenance()
        await self._storage.async_set_flag("daily_briefing_enviado", "true")
        self._hass.bus.async_fire(EVENT_SLEEP_COMPLETE)
        _LOGGER.info(
            "Sleep Consolidation done: %d memories (%d new, %d reinforced), "
            "%d restrictions",
            len(memorias), applied["new"], applied["reinforced"],
            restrictions_applied,
        )
        return {
            "suppressed": False, "briefing": True,
            "memories": applied, "restrictions": restrictions_applied,
            "maintenance": maintenance,
        }

    # ------------------------------------------------------------------
    # Prompts (PT — resident-facing briefing content)
    # ------------------------------------------------------------------

    def _load_prompt_files(self) -> tuple:
        agent_autos = []
        path = self._hass.config.path(AGENT_AUTOMATIONS_RELATIVE_PATH)
        try:
            raw = load_yaml(path)
            if isinstance(raw, list):
                agent_autos = raw
        except (FileNotFoundError, OSError):
            pass
        except Exception as exc:  # noqa: BLE001 — malformed YAML must not kill the cycle
            _LOGGER.warning("Cannot parse %s: %s", path, exc)
        return agent_autos, circuit_health_summary(self._hass)

    @staticmethod
    def _build_briefing_prompt(
        eventos, n_interacoes, pendencias, sugestoes, agent_autos, health_line
    ) -> str:
        now = datetime.now()
        dia_pt = DAYS_PT[now.weekday()]
        data_str = now.strftime("%d/%m/%Y")

        if agent_autos:
            linhas = [f"  {i+1}. {a.get('alias','?')} (id: {a.get('id','?')})"
                      for i, a in enumerate(agent_autos)]
            autos_txt = ("AUTOMACOES DO AGENTE (revise se ainda sao uteis):\n"
                         + "\n".join(linhas))
        else:
            autos_txt = "AUTOMACOES DO AGENTE: nenhuma criada."

        eventos_txt = (
            "; ".join(f"{e.get('ts','?')[11:16]} {e.get('detalhe','?')}"
                      for e in eventos)
            if eventos else "nenhum"
        )
        pendencias_txt = "; ".join(pendencias[:3]) if pendencias else "nenhuma"
        sugestoes_txt = "; ".join(sugestoes[:3]) if sugestoes else "nenhuma"
        health_section = f"\n{health_line}\n" if health_line else ""

        return f"""Produza o briefing residencial de {dia_pt}, {data_str}.
IMPORTANTE: Retorne APENAS o texto. Maximo 120 palavras. Sem emojis, sem markdown avancado.
Estruture em topicos curtos (3-4 linhas cada), nao em paragrafo corrido.
Exclua: erros de framework, mensagens de teste, falhas de provedor LLM, erros do proprio sistema PERMEAR.
Apenas comportamento real da casa conta.

{autos_txt}

EVENTOS DO DIA (ultimos 10): {eventos_txt}
INTERACOES HOJE: {n_interacoes} registradas.
PENDENCIAS: {pendencias_txt}
SUGESTOES DE AUTOMACAO PENDENTES: {sugestoes_txt}
{health_section}
INSTRUCOES:
1. Se ha automacoes do agente listadas, mencione-as brevemente e pergunte se ainda sao uteis.
2. Resuma o dia em 2-3 topicos. Destaque o incomum.
3. Mencione pendencias relevantes brevemente.
4. Se ha sugestoes de automacao pendentes, apresente a mais relevante.
5. Se nada especial, diga em uma frase e acrescente algo util."""

    @staticmethod
    def _build_extraction_prompt(eventos, interacoes) -> str:
        eventos_slim = [
            {"ts": e.get("ts", ""), "detalhe": e.get("detalhe", ""),
             "entity_id": e.get("entity_id")}
            for e in eventos
        ]
        return f"""Analyze today's events and interactions and extract up to 5
relevant memories (not trivialities). Short, factual phrases
that make sense to re-read days later, in Brazilian Portuguese.

EXCLUDE: framework errors, LLM/provider failures, Telegram
commands, test messages, and any PERMEAR system operational
issues. Only real household behavior counts.

SYNTHESIZE: prefer synthesis over repeating individual entity
events already captured by the hourly heartbeat — those are
already stored with entity keys and don't need to be re-listed.

For each memory about a specific HA entity, append
[entity:<entity_id>] at the end of the memory text
(e.g. "Cortina fechada automaticamente à noite [entity:cover.curtain_example]").
Only for single-entity memories — not for general summaries.

RESTRICTIONS (separate field 'restricoes'): when an interaction shows the
resident asking NOT to be notified about something or saying a subject is
irrelevant ("para de avisar da geladeira", "isso não importa", "não me fala
disso"), return one short PT-BR phrase per subject in 'restricoes', appending
[entity:<entity_id>] when it maps to exactly ONE entity from today's events.
Never invent restrictions — only what the resident actually expressed.
Return an empty list when there is none.

Today's events: {json.dumps(eventos_slim, ensure_ascii=False)}
Interactions: {json.dumps(interacoes, ensure_ascii=False)}

If nothing is relevant, return an empty list."""

    @staticmethod
    def _simple_briefing(n_eventos, n_interacoes, pendencias) -> str:
        """Deterministic PT fallback (ports sleep_simple.py). Persists nothing."""
        now = datetime.now()
        partes = [
            f"Briefing de {DAYS_PT[now.weekday()]}, {now.strftime('%d/%m/%Y')}.",
            f"Hoje foram registrados {n_eventos} eventos e "
            f"{n_interacoes} interacoes.",
        ]
        if pendencias:
            partes.append(f"Pendencias em aberto: {pendencias[0]}")
            if len(pendencias) > 1:
                partes.append(f"Tambem ha: {pendencias[1]}")
        partes.append("Briefing completo indisponivel agora. "
                      "Tente perguntar diretamente caso queira detalhes.")
        return " ".join(partes)

    # ------------------------------------------------------------------
    # Memory application (ports apply_sleep_memories.py)
    # ------------------------------------------------------------------

    async def _apply_memories(self, memorias: list) -> dict:
        valid_ids = await self._hass.async_add_executor_job(self._valid_entity_ids)
        new_c = reinforced = skipped = 0
        for raw in memorias:
            raw = str(raw or "").strip()
            if not raw:
                continue
            content, entity_id = self._parse_memory(raw)
            if not content:
                skipped += 1
                continue
            # Key only when the extraction names ONE valid entity (rule: never
            # synthetic-keyed — invalid/absent tag falls back to FTS, keyless)
            key = f"observation:{entity_id}" if entity_id in valid_ids else None
            _, was_new, _ = await self._storage.async_add_or_reinforce(
                content, kind="observation", source="daily", key=key
            )
            if was_new:
                new_c += 1
            else:
                reinforced += 1
        return {"new": new_c, "reinforced": reinforced, "skipped": skipped}

    async def _apply_restrictions(self, restricoes: list) -> int:
        """Persist restriction intents as Organic Memory (v9.0.2).

        kind='behavior_rule', source='interaction' (never promotes — a
        restriction only needs to EXIST to be read), metadata.restriction.
        Key 'restriction:<entity_id>' when the speech names ONE resolvable
        entity (own namespace — must never reinforce the event memory);
        vague subjects stay keyless and merge via the FTS layer. Reinforced
        when repeated; fades by normal tier decay when never mentioned again
        (a forgotten restriction re-emerges — organic, intentional).
        """
        if not restricoes:
            return 0
        valid_ids = await self._hass.async_add_executor_job(self._valid_entity_ids)
        applied = 0
        for raw in restricoes:
            raw = str(raw or "").strip()
            if not raw:
                continue
            content, entity_id = self._parse_memory(raw)
            if not content:
                continue
            eid = entity_id if entity_id in valid_ids else None
            metadata = {"restriction": True}
            if eid:
                metadata["entity_id"] = eid
            await self._storage.async_add_or_reinforce(
                content, kind="behavior_rule", source="interaction",
                key=f"restriction:{eid}" if eid else None, metadata=metadata,
            )
            applied += 1
        return applied

    @staticmethod
    def _parse_memory(raw: str) -> tuple:
        m = ENTITY_TAG.search(raw)
        if not m:
            return raw.strip(), None
        return raw[: m.start()].strip(), m.group(1).strip()

    def _valid_entity_ids(self) -> set:
        data = load_json(
            self._hass.config.path(MONITORED_ENTITIES_RELATIVE_PATH),
            {"entities": []},
        )
        return {
            e["entity_id"]
            for e in data.get("entities", [])
            if isinstance(e, dict) and e.get("entity_id")
        }
