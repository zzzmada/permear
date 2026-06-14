"""HA update notifications, in-process (v9.0-final, PM decision #3: keep).

Replaces ha_update_manager.py + ha_updates_check.py + the update-card block
of the shell Sleep automation. No REST, no Supervisor API, no token:

- detection reads the native update.* entities from hass.states (state "on"
  = update available; skipped_version set = user ignored it);
- execute/skip call the update.install / update.skip services;
- the Supervisor backup check/create was dropped — its result was never
  shown to the user in the shell flow, and the update entities path needs
  no Supervisor access.

Daily check at 09:05 LOCAL (morning slot, right after Wake — the shell sent
these at 23:30 attached to the Sleep briefing). One PT card per update with
Atualizar/Ignorar buttons; callbacks are handled by the Telegram handler.
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change

from .const import UPDATES_TIME
from .notify import async_send_telegram

_LOGGER = logging.getLogger(__name__)


class PermearUpdates:
    """Daily update detection + execute/skip actions for the callbacks."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._unsub = None

    @callback
    def start(self) -> None:
        hour, minute = (int(p) for p in UPDATES_TIME.split(":"))
        self._unsub = async_track_time_change(
            self._hass, self._on_time, hour=hour, minute=minute, second=0
        )
        _LOGGER.info("Update check scheduled at %s local", UPDATES_TIME)

    @callback
    def stop(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    async def _on_time(self, _now) -> None:
        try:
            await self.async_run()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Update check failed")

    # ------------------------------------------------------------------
    # Detection (ports cmd_list_pending_json — addons, core, OS order)
    # ------------------------------------------------------------------

    def pending_updates(self) -> list[dict]:
        addons, core, haos = [], [], []
        for state in self._hass.states.async_all("update"):
            if state.state != "on":
                continue
            attrs = state.attributes
            if attrs.get("skipped_version"):
                continue
            entry = {
                "entity_id": state.entity_id,
                "name": attrs.get("friendly_name", state.entity_id),
                "current": attrs.get("installed_version", "?"),
                "latest": attrs.get("latest_version", "?"),
            }
            eid_lower = state.entity_id.lower()
            if "homeassistant" in eid_lower and "os" in eid_lower:
                haos.append(entry)
            elif "core" in eid_lower:
                core.append(entry)
            else:
                addons.append(entry)
        return addons + core + haos

    async def async_run(self) -> int:
        """Send the daily update cards. Returns how many were sent."""
        updates = self.pending_updates()
        if not updates:
            return 0
        await async_send_telegram(
            self._hass,
            f"{len(updates)} atualizacao(oes) disponivel(eis):",
        )
        for u in updates:
            await async_send_telegram(
                self._hass,
                f"{u['name']}: {u['current']} para {u['latest']}\n"
                f"[entity:{u['entity_id']}]",
                inline_keyboard=["Atualizar:/Atualizar, Ignorar:/Ignorar"],
            )
        _LOGGER.info("Update cards sent: %d", len(updates))
        return len(updates)

    # ------------------------------------------------------------------
    # Actions (Telegram callbacks)
    # ------------------------------------------------------------------

    def _friendly(self, entity_id: str) -> str:
        state = self._hass.states.get(entity_id)
        if state is None:
            return entity_id
        return state.attributes.get("friendly_name", entity_id)

    async def async_execute(self, entity_id: str) -> str:
        """Start an update via the native service. Returns PT result text."""
        if not entity_id.startswith("update."):
            return f"Entidade invalida: {entity_id}."
        try:
            await self._hass.services.async_call(
                "update", "install", {"entity_id": entity_id}, blocking=False
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("update.install %s failed: %s", entity_id, exc)
            return f"Erro ao iniciar a atualizacao de {self._friendly(entity_id)}."
        return f"Atualizacao iniciada: {self._friendly(entity_id)}."

    async def async_skip(self, entity_id: str) -> str:
        """Skip this version. Returns PT result text."""
        try:
            await self._hass.services.async_call(
                "update", "skip", {"entity_id": entity_id}, blocking=True
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("update.skip %s failed: %s", entity_id, exc)
            return f"Erro ao ignorar a atualizacao de {self._friendly(entity_id)}."
        return (f"Atualizacao ignorada: {self._friendly(entity_id)}. "
                "Voce sera avisado na proxima versao.")
