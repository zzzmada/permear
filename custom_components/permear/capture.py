"""In-process event capture (v8.8) — replaces events.yaml + record_event.py.

Listens to state changes of the entities marked monitor=true in
/config/memory/monitored_entities.json and persists each occurrence to the
Organic Memory database (event_buffer + event_log dual write).

Per-domain metadata is extracted directly from the new state object — no
JSON-via-shell, no base64 transport, no input_text staging. The metadata
contract is the closed list in const.METADATA_ATTRIBUTES; None values are
omitted (no more cosmetic '{"position": ""}' for the wrong types).

Behavior rules carried over from the shell chain:
- entity_id rejected when invalid ('-', 'while', 'mesmo', empty, no dot);
- domain derived from the entity_id string, never from a state attribute;
- ts in LOCAL time (datetime.now());
- HA errors never enter the buffer — only state changes of monitored entities;
- cover changes < COVER_DEBOUNCE_SECONDS apart for the same entity are dropped
  (hardware flapping must not inflate the log).

New in the in-process capture (not expressible in the old static triggers):
- attribute-only updates (old state == new state) are skipped;
- transitions to/from unknown/unavailable are skipped (availability is a
  health signal handled globally, not a household event);
- occupancy/motion/presence binary_sensors are recorded as TWO events per
  occupancy span — the ARRIVAL (-> on that sustains past the debounce, the
  salience candidate "presence detected", metadata {}) and the CLEARING
  (-> off, with occupied_for_s in metadata from last_changed) — instead of
  every on/off toggle. A span shorter than OCCUPANCY_DEBOUNCE_SECONDS is a
  transient pass-through: the pending arrival is cancelled and the clearing is
  dropped, so a flap produces ZERO events. Other binary_sensors (door, window,
  …) are unchanged — every transition is still recorded.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from functools import partial
from typing import Callable

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
)
from homeassistant.util import dt as dt_util

from .const import (
    CAPTURE_DOMAINS,
    COVER_DEBOUNCE_SECONDS,
    IGNORED_STATES,
    INVALID_ENTITY_IDS,
    METADATA_ATTRIBUTES,
    MONITORED_ENTITIES_RELATIVE_PATH,
    OCCUPANCY_DEBOUNCE_SECONDS,
    PRESENCE_DEVICE_CLASSES,
)
from .storage import PermearStorage

_LOGGER = logging.getLogger(__name__)


def _valid_entity_id(entity_id: str | None) -> bool:
    if not entity_id:
        return False
    cleaned = entity_id.strip()
    return cleaned not in INVALID_ENTITY_IDS and "." in cleaned


class PermearCapture:
    """Registers the state-change listener and dispatches writes."""

    def __init__(self, hass: HomeAssistant, storage: PermearStorage) -> None:
        self._hass = hass
        self._storage = storage
        self._unsub = None
        self._last_cover_event: dict[str, float] = {}
        self._light_on_since: dict[str, float] = {}
        # Presence arrival timers awaiting debounce confirmation, by entity_id.
        self._pending_arrival: dict[str, Callable[[], None]] = {}

    async def async_start(self) -> None:
        """Read the monitored-entity list and register the listener."""
        await self.async_refresh()

    async def async_refresh(self) -> None:
        """(Re-)read the monitored-entity list and (re-)register the listener.

        Called at setup and by Wake after it updates the list — without this,
        a fresh install (no monitored_entities.json yet) stayed inert until
        the next restart even after Wake discovered the entities."""
        path = self._hass.config.path(MONITORED_ENTITIES_RELATIVE_PATH)
        entities = await self._hass.async_add_executor_job(
            self._load_monitored, path
        )
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        if not entities:
            _LOGGER.warning(
                "No monitored entities found at %s — capture idle until "
                "Wake discovers entities", path
            )
            return
        self._unsub = async_track_state_change_event(
            self._hass, entities, self._handle_state_change
        )
        _LOGGER.info("PERMEAR capture listening to %d entities", len(entities))

    @staticmethod
    def _load_monitored(path: str) -> list[str]:
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            return []
        except (json.JSONDecodeError, OSError) as exc:
            _LOGGER.warning("Cannot read %s (%s) — capture disabled", path, exc)
            return []
        return [
            ent["entity_id"]
            for ent in data.get("entities", [])
            if ent.get("monitor") is True and _valid_entity_id(ent.get("entity_id"))
        ]

    @callback
    def _handle_state_change(self, event: Event) -> None:
        """Lightweight listener: filter, extract metadata, dispatch the write."""
        entity_id: str | None = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")

        if new_state is None or not _valid_entity_id(entity_id):
            return

        # Domain filter — only household-event domains pass through
        domain = entity_id.split(".", 1)[0]
        if domain not in CAPTURE_DOMAINS:
            return
        if new_state.state in IGNORED_STATES:
            return
        if old_state is not None and old_state.state in IGNORED_STATES:
            return
        # Attribute-only updates are not household events.
        if old_state is not None and old_state.state == new_state.state:
            return

        now_mono = time.monotonic()

        # Occupancy/motion/presence: two events per span (arrival + clearing),
        # debounced, instead of every toggle. Handled entirely on its own path.
        if (domain == "binary_sensor"
                and self._is_presence(new_state, old_state)):
            self._handle_presence(entity_id, old_state, new_state)
            return

        if domain == "cover":
            last = self._last_cover_event.get(entity_id)
            if last is not None and (now_mono - last) < COVER_DEBOUNCE_SECONDS:
                return
            self._last_cover_event[entity_id] = now_mono
        metadata = self._extract_metadata(domain, entity_id, new_state, now_mono)

        ts = datetime.now().isoformat()  # LOCAL time — never UTC
        object_id = entity_id.split(".", 1)[1]
        detalhe = f"{object_id}_{new_state.state}"

        self._hass.async_create_task(
            self._async_write(ts, entity_id, detalhe, json.dumps(metadata))
        )

    def _extract_metadata(
        self, domain: str, entity_id: str, new_state, now_mono: float
    ) -> dict:
        """Closed-list per-domain metadata from the state object."""
        attr_map = METADATA_ATTRIBUTES.get(domain)
        if attr_map is None:
            return {}
        metadata = {}
        for attr, key in attr_map.items():
            value = new_state.attributes.get(attr)
            if value is not None:
                metadata[key] = value
        if domain == "light":
            if new_state.state == "on":
                self._light_on_since[entity_id] = now_mono
            elif new_state.state == "off":
                on_since = self._light_on_since.pop(entity_id, None)
                if on_since is not None:
                    metadata["duration_s"] = round(now_mono - on_since)
        return metadata

    @staticmethod
    def _is_presence(new_state, old_state) -> bool:
        """True if this binary_sensor reports occupancy/motion/presence."""
        device_class = new_state.attributes.get("device_class")
        if device_class is None and old_state is not None:
            device_class = old_state.attributes.get("device_class")
        return device_class in PRESENCE_DEVICE_CLASSES

    def _handle_presence(self, entity_id: str, old_state, new_state) -> None:
        """Presence as two events per occupancy span — arrival and clearing.

        The 10s debounce is realised prospectively for the arrival and
        retrospectively for the clearing, and the two agree at the boundary:

        - Becoming occupied (-> 'on'): schedule a confirmation timer one debounce
          ahead. If it survives (no clearing cancels it), the 'on' has sustained
          and we record ONE arrival event ("<object>_on", metadata {} — the
          arrival has no duration yet). This is the salience candidate the ARAS
          may flag (e.g. presence at an odd hour).
        - Clearing (-> 'off'): if an arrival is still pending, the 'on' never
          sustained past the debounce — cancel it; flap, no arrival and no
          clearing (ZERO events). Otherwise the arrival already fired, so record
          the clearing tagged with occupied_for_s (always >= debounce here).

        A composite flap (on->off->on within the window) cancels the first
        pending arrival and re-arms on the second 'on'; the arrival counts only
        once the 'on' finally stabilises — never twice.
        """
        object_id = entity_id.split(".", 1)[1]

        if new_state.state == "on":
            # Re-arm: cancel any stale pending arrival (defensive; on->on is
            # already filtered as an attribute-only update upstream).
            self._cancel_pending_arrival(entity_id)
            self._pending_arrival[entity_id] = async_call_later(
                self._hass,
                OCCUPANCY_DEBOUNCE_SECONDS,
                partial(self._confirm_arrival, entity_id, object_id),
            )
            return

        # Clearing transition (-> 'off'; unknown/unavailable already filtered).
        pending = self._pending_arrival.pop(entity_id, None)
        if pending is not None:
            pending()  # 'on' never sustained — flap: drop arrival and clearing
            return

        metadata = self._exit_metadata(old_state)
        ts = datetime.now().isoformat()  # LOCAL time — never UTC
        detalhe = f"{object_id}_off"
        self._hass.async_create_task(
            self._async_write(ts, entity_id, detalhe, json.dumps(metadata))
        )

    @callback
    def _confirm_arrival(self, entity_id: str, object_id: str, _now) -> None:
        """Timer fired — the 'on' sustained past the debounce. Record arrival."""
        self._pending_arrival.pop(entity_id, None)
        ts = datetime.now().isoformat()  # LOCAL time — never UTC
        detalhe = f"{object_id}_on"
        self._hass.async_create_task(
            self._async_write(ts, entity_id, detalhe, json.dumps({}))
        )

    @callback
    def _cancel_pending_arrival(self, entity_id: str) -> None:
        pending = self._pending_arrival.pop(entity_id, None)
        if pending is not None:
            pending()

    @staticmethod
    def _exit_metadata(old_state) -> dict:
        """occupied_for_s for the clearing event, from the 'on' span length."""
        if old_state is None or old_state.last_changed is None:
            return {}  # no start reference (e.g. just after a restart)
        # A duration is a delta, so timezone-agnostic; last_changed and
        # dt_util.utcnow() are both UTC-aware. The stored event ts stays LOCAL
        # (set by the caller via datetime.now()) — no UTC leak there.
        occupied_for_s = round(
            (dt_util.utcnow() - old_state.last_changed).total_seconds()
        )
        return {"occupied_for_s": occupied_for_s}

    async def _async_write(
        self, ts: str, entity_id: str, detalhe: str, metadata: str
    ) -> None:
        try:
            await self._storage.async_add_event(ts, entity_id, detalhe, metadata)
        except Exception:  # noqa: BLE001 — capture must never crash HA
            _LOGGER.exception("Failed to persist event for %s", entity_id)

    @callback
    def stop(self) -> None:
        """Unregister the listener and cancel any pending arrival timers."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        for cancel in self._pending_arrival.values():
            cancel()
        self._pending_arrival.clear()
