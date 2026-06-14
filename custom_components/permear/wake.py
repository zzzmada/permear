"""Wake — daily entity discovery, in-process (v8.10).

Replaces the shell chain events.yaml entity-sync automation +
discover_entities.py (REST /api/states + raw .storage read).

Flow (unchanged from production):
  read the entities exposed to conversation → sync monitored_entities.json
  (preserving monitor flags, priorities and events fields; entities no longer
  exposed get monitor=False) → new entities of a sensitive class (smoke,
  water, gas, …) → ONE Telegram priority card each (PT, inline keyboard;
  callbacks stay with telegram.yaml until v9.0).

In-process notes: exposure comes live from exposed_entities
(async_should_expose — covers default exposure, not only the per-entity
registry options the shell read raw from .storage). States/attributes come
from hass.states. pending_priority.json is no longer written — the card is
sent directly. Fixed time 09:00 LOCAL (as the shell automation); also run
once right after setup when monitored_entities.json does not exist yet.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from homeassistant.components.homeassistant.exposed_entities import (
    async_should_expose,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change

from .const import (
    MONITORED_ENTITIES_RELATIVE_PATH,
    SENSITIVE_DEVICE_CLASSES,
    SENSITIVE_DOMAINS,
    WAKE_TIME,
)
from .notify import async_send_telegram
from .storage import locked_json_update

_LOGGER = logging.getLogger(__name__)

# Fallback discovery when nothing is exposed to conversation (shell parity).
FALLBACK_DOMAINS = (
    "light", "switch", "binary_sensor", "sensor", "climate",
    "media_player", "cover", "fan", "input_boolean", "lock",
)
FALLBACK_SKIP_PREFIXES = (
    "sensor.time", "sensor.date", "sensor.last_boot",
    "sensor.sun", "sun.sun", "weather.",
)


class PermearWake:
    """Schedules and runs the daily entity discovery."""

    def __init__(self, hass: HomeAssistant, capture=None) -> None:
        self._hass = hass
        self._capture = capture  # PermearCapture — re-subscribed after sync
        self._unsub = None
        self._task: asyncio.Task | None = None
        self._running = False

    @callback
    def start(self) -> None:
        hour, minute = (int(p) for p in WAKE_TIME.split(":"))
        self._unsub = async_track_time_change(
            self._hass, self._on_time, hour=hour, minute=minute, second=0
        )
        _LOGGER.info("Wake (entity discovery) scheduled at %s local", WAKE_TIME)

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
            return
        self._running = True
        self._task = asyncio.current_task()
        try:
            await self.async_run()
        except Exception:  # noqa: BLE001 — the cycle must never crash HA
            _LOGGER.exception("Wake discovery failed")
        finally:
            self._running = False
            self._task = None

    # ------------------------------------------------------------------
    # The cycle
    # ------------------------------------------------------------------

    async def async_run(self) -> dict:
        # async_should_expose covers default exposure too — the registry
        # option only exists for entities the user toggled manually, which
        # made Wake miss everything exposed by default on a fresh install.
        exposed_ids = {
            s.entity_id
            for s in self._hass.states.async_all()
            if async_should_expose(self._hass, "conversation", s.entity_id)
        }

        # Plain-dict state snapshot, built on the loop, consumed in executor
        states = {
            s.entity_id: {
                "friendly_name": s.attributes.get("friendly_name", s.entity_id),
                "device_class": s.attributes.get("device_class", "") or "",
            }
            for s in self._hass.states.async_all()
        }

        result = await self._hass.async_add_executor_job(
            self._sync_monitored, exposed_ids, states
        )
        _LOGGER.info(
            "Wake: %d entities (%d monitored, source %s), %d sensitive new",
            result["total"], result["monitored"], result["source"],
            len(result["sensitive_new"]),
        )

        # Re-subscribe capture to the fresh list (no restart needed)
        if self._capture is not None:
            await self._capture.async_refresh()

        for ent in result["sensitive_new"]:
            await self._send_priority_card(ent)
        return result

    def _sync_monitored(self, exposed_ids: set, states: dict) -> dict:
        """Merge discovery into monitored_entities.json (executor, flock)."""
        path = self._hass.config.path(MONITORED_ENTITIES_RELATIVE_PATH)
        with locked_json_update(path, {"entities": []}) as data:
            existing = {}
            for entry in data.get("entities", []):
                if isinstance(entry, dict) and entry.get("entity_id"):
                    existing[entry["entity_id"]] = entry

            entities = []
            if exposed_ids:
                source = "entity_registry"
                for entity_id in sorted(exposed_ids):
                    state = states.get(entity_id)
                    friendly = state["friendly_name"] if state else entity_id
                    if entity_id in existing:
                        entry = dict(existing[entity_id])
                        entry["friendly_name"] = friendly
                        # Re-exposed entity: restore monitoring only when WE
                        # turned it off — user-disabled entries stay off.
                        if (entry.get("monitor") is False
                                and entry.get("monitor_source") == "wake"):
                            entry["monitor"] = True
                            entry.pop("monitor_source", None)
                    else:
                        entry = {
                            "entity_id": entity_id,
                            "friendly_name": friendly,
                            "domain": entity_id.split(".")[0],
                            "monitor": True,
                        }
                    entities.append(entry)
                for entity_id, entry in existing.items():
                    if entity_id not in exposed_ids:
                        entry = dict(entry)
                        if entry.get("monitor") is not False:
                            entry["monitor_source"] = "wake"  # system-disabled
                        entry["monitor"] = False
                        entities.append(entry)
            else:
                source = "domain_filter"
                for entity_id, state in states.items():
                    if entity_id.split(".")[0] not in FALLBACK_DOMAINS:
                        continue
                    if entity_id.startswith(FALLBACK_SKIP_PREFIXES):
                        continue
                    if entity_id in existing:
                        entities.append(existing[entity_id])
                    else:
                        entities.append({
                            "entity_id": entity_id,
                            "friendly_name": state["friendly_name"],
                            "domain": entity_id.split(".")[0],
                            "monitor": True,
                        })

            entities.sort(key=lambda x: x["entity_id"])
            monitored = sum(1 for e in entities if e.get("monitor", True))

            candidate_ids = exposed_ids if exposed_ids else set(states)
            sensitive_new = self._detect_sensitive_new(
                [eid for eid in candidate_ids if eid not in existing], states
            )

            data.clear()
            data.update({
                "updated_at": datetime.now().isoformat(),
                "source": source,
                "count": monitored,
                "entities": entities,
            })
        return {
            "total": len(entities),
            "monitored": monitored,
            "source": source,
            "sensitive_new": sensitive_new,
        }

    @staticmethod
    def _detect_sensitive_new(new_entity_ids: list, states: dict) -> list:
        out = []
        for eid in new_entity_ids:
            state = states.get(eid, {})
            dc = state.get("device_class", "")
            if eid.split(".")[0] in SENSITIVE_DOMAINS or dc in SENSITIVE_DEVICE_CLASSES:
                out.append({
                    "entity_id": eid,
                    "friendly_name": state.get("friendly_name", eid),
                    "device_class": dc,
                })
        return out

    async def _send_priority_card(self, ent: dict) -> None:
        """Priority question for a new sensitive device (PT, rule #24 keyboard).
        The /prio_set_* callbacks are handled by telegram.yaml until v9.0."""
        eid = ent["entity_id"]
        message = (
            f"Detectei um dispositivo novo sensível: {ent['friendly_name']} "
            f"({eid})\n\n"
            "Quão importante é para você ser avisado sobre este sensor?"
        )
        keyboard = [
            f"Sempre:/prio_set_2_{eid}, Só se anormal:/prio_set_1_{eid}",
            f"Ignorar:/prio_set_0_{eid}",
        ]
        await async_send_telegram(self._hass, message, inline_keyboard=keyboard)
