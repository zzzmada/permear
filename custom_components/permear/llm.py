"""ai_task client with the standard fallback choreography (v8.10).

One implementation of the pattern every PERMEAR cycle uses for its data-LLM
call (cycles.yaml choose+default+if/then, rule #20):

  - a fallback was logged < 1h ago  → skip primary, go straight to fallback
  - otherwise call primary          → empty/failed response → call fallback
  - both fail                       → None (the cycle fails honestly — no
                                      degraded mode, Reading B)

Sleep and Systems use this client. The Heartbeat (v8.9, frozen) keeps its own
inline copy of the same choreography — unifying it onto this module is v9.0
cleanup, not touched here.

agent_circuit.json is the live fallback signal, flock-shared with the shell
cycles during coexistence. All file I/O runs in the executor.
"""

from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.core import HomeAssistant

from .config import PermearConfig
from .const import (
    AGENT_CIRCUIT_RELATIVE_PATH,
    ARCHIVED_ERRORS_RELATIVE_PATH,
    FALLBACK_SKIP_PRIMARY_SECONDS,
)
from .storage import load_json, locked_json_update

_LOGGER = logging.getLogger(__name__)


class AiTaskClient:
    """Data-provider ai_task calls with primary→fallback choreography."""

    def __init__(self, hass: HomeAssistant, config: PermearConfig) -> None:
        self._hass = hass
        self._config = config

    async def async_generate(
        self, task_name: str, instructions: str, structure: dict
    ) -> dict | None:
        """ONE logical LLM call. Returns the response data dict, or None when
        no provider answered (honest failure — callers decide the fallback)."""
        if not self._config.data and not self._config.data_fallback:
            _LOGGER.error(
                "No data provider configured in permear.yaml — %s skipped",
                task_name,
            )
            return None

        recent_fb = await self._hass.async_add_executor_job(self._recent_fallback)

        if recent_fb and self._config.data_fallback:
            await self._hass.async_add_executor_job(self._log_fallback)
            return await self._call(
                self._config.data_fallback,
                f"{task_name} [skip-primary]",
                instructions,
                structure,
            )

        data = None
        if self._config.data:
            data = await self._call(
                self._config.data, task_name, instructions, structure
            )
        if data is None and self._config.data_fallback:
            await self._hass.async_add_executor_job(self._log_fallback)
            data = await self._call(
                self._config.data_fallback,
                f"{task_name} [fallback]",
                instructions,
                structure,
            )
        return data

    async def _call(
        self, entity_id: str, task_name: str, instructions: str, structure: dict
    ) -> dict | None:
        try:
            resp = await self._hass.services.async_call(
                "ai_task",
                "generate_data",
                {
                    "task_name": task_name,
                    "entity_id": entity_id,
                    "instructions": instructions,
                    "structure": structure,
                },
                blocking=True,
                return_response=True,
            )
        except Exception as exc:  # noqa: BLE001 — 429/Timeout still propagate
            _LOGGER.warning("ai_task %s via %s failed: %s", task_name, entity_id, exc)
            return None
        data = (resp or {}).get("data")
        if not isinstance(data, dict) or not data:
            return None
        return data

    async def async_log_fallback(self) -> None:
        """Public fallback log — the conversation path (Telegram handler)
        shares the same agent_circuit.json signal as the data path."""
        await self._hass.async_add_executor_job(self._log_fallback)

    def _recent_fallback(self) -> bool:
        circuit = load_json(self._hass.config.path(AGENT_CIRCUIT_RELATIVE_PATH), {})
        raw = circuit.get("last_fallback_at")
        if not raw:
            return False
        try:
            last_fb = datetime.fromisoformat(raw)
        except (ValueError, TypeError):
            return False
        delta = (datetime.now() - last_fb).total_seconds()
        return 0 <= delta < FALLBACK_SKIP_PRIMARY_SECONDS

    def _log_fallback(self) -> None:
        """Same agent_circuit.json shape as log_fallback.py / heartbeat v8.9."""
        today = datetime.now().strftime("%Y-%m-%d")
        path = self._hass.config.path(AGENT_CIRCUIT_RELATIVE_PATH)
        with locked_json_update(path, {}) as circuit:
            stats = circuit.get("daily_stats") or {}
            if stats.get("date") != today:
                stats = {"date": today, "errors_503_seen": 0,
                         "retries_recovered": 0, "failures_3x": 0,
                         "circuit_opens": 0, "fallbacks": 0}
            stats["fallbacks"] = stats.get("fallbacks", 0) + 1
            circuit["daily_stats"] = stats
            circuit["last_fallback_at"] = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )


def circuit_health_summary(hass: HomeAssistant) -> str:
    """Read-only port of lib/agent.get_health_summary_for_prompt (PT strings).

    Used by the Sleep prompt. Executor only — reads two JSON files. The
    Heartbeat keeps its private copy (v8.9 frozen); unify in v9.0.
    """
    circuit = load_json(hass.config.path(AGENT_CIRCUIT_RELATIVE_PATH), {})
    today = datetime.now().strftime("%Y-%m-%d")
    raw_stats = circuit.get("daily_stats") or {}
    stats = raw_stats if raw_stats.get("date") == today else {}

    archived = load_json(
        hass.config.path(ARCHIVED_ERRORS_RELATIVE_PATH), {"errors": {}}
    )
    archived_count = len(archived.get("errors", {}))

    open_until = None
    raw_open = circuit.get("circuit_open_until")
    if raw_open:
        try:
            open_until = datetime.fromisoformat(raw_open)
        except (ValueError, TypeError):
            open_until = None
    if open_until and datetime.now() < open_until:
        return (f"Saúde: circuit breaker aberto até "
                f"{open_until.strftime('%H:%M')}, sistema degradado.")

    failures = stats.get("failures_3x", 0)
    retries_ok = stats.get("retries_recovered", 0)
    if failures >= 2:
        return f"Saúde: {failures} falhas finais hoje após retries — atenção."
    if archived_count >= 5:
        return f"Saúde: {archived_count} erros silenciados ativos."
    if retries_ok >= 2:
        return f"Saúde: agente recuperou de {retries_ok} hiccups hoje via retry."
    return ""
