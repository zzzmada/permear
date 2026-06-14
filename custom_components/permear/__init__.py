"""PERMEAR — cognitive memory and salience layer for Home Assistant.

v8.8: in-process event capture (state-change listener → SQLite dual write).
v8.9: in-process Heartbeat + ARAS + native status sensors.
v8.10: in-process Sleep, Systems and Wake cycles (the shell automations stay
until Hermes validates and cuts over — coexistence by design).
v9.0: config lives in the config entry (config_flow + options_flow); error
monitor, Telegram handler (conversation + callbacks + agent automations CRUD)
and the HA update cards are in-process — ZERO runtime shell remains. Saving
options reloads the entry so everything re-reads the config without restart.
The daily DB cleanup (buffer prune / event_log retention / daily flags) and
the first-run Wake bootstrap are in-process too.

Config entry only — no YAML setup.
"""

from __future__ import annotations

import logging
import os

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.start import async_at_started

from .agent_automations import AgentAutomations
from .capture import PermearCapture
from .config import config_from_entry
from .const import (
    DAILY_CLEANUP_TIME,
    DB_RELATIVE_PATH,
    DOMAIN,
    MONITORED_ENTITIES_RELATIVE_PATH,
)
from .error_monitor import PermearErrorMonitor
from .heartbeat import PermearHeartbeat
from .llm import AiTaskClient
from .sleep import PermearSleep
from .storage import PermearStorage
from .systems import PermearSystems
from .telegram_handler import PermearTelegramHandler
from .updates import PermearUpdates
from .wake import PermearWake

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Open the Organic Memory store, start capture, cycles and sensors.

    Every started subsystem registers its stop via entry.async_on_unload —
    if anything later in setup raises, HA still runs those callbacks, so a
    failed setup never leaks listeners, timers or the SQLite connection.
    """
    config = config_from_entry(entry)

    storage = PermearStorage(hass, hass.config.path(DB_RELATIVE_PATH))
    await storage.async_init()
    entry.async_on_unload(storage.async_close)

    capture = PermearCapture(hass, storage)
    await capture.async_start()
    entry.async_on_unload(capture.stop)

    heartbeat = PermearHeartbeat(hass, storage, config)
    heartbeat.start()
    entry.async_on_unload(heartbeat.stop)

    llm = AiTaskClient(hass, config)
    sleep = PermearSleep(hass, storage, config, llm)
    sleep.start()
    entry.async_on_unload(sleep.stop)
    systems = PermearSystems(hass, storage, config, llm)
    systems.start()
    entry.async_on_unload(systems.stop)
    wake = PermearWake(hass, capture)
    wake.start()
    entry.async_on_unload(wake.stop)

    error_monitor = PermearErrorMonitor(hass)
    error_monitor.start()
    entry.async_on_unload(error_monitor.stop)
    updates = PermearUpdates(hass)
    updates.start()
    entry.async_on_unload(updates.stop)
    telegram = PermearTelegramHandler(
        hass, storage, config, llm, AgentAutomations(hass), updates
    )
    telegram.start()
    entry.async_on_unload(telegram.stop)

    # Daily DB cleanup — ports the deleted shell maintenance (00:05 local)
    async def _daily_cleanup(_now) -> None:
        try:
            await storage.async_daily_cleanup()
        except Exception:  # noqa: BLE001 — maintenance must never crash HA
            _LOGGER.exception("Daily DB cleanup failed")

    hour, minute = (int(p) for p in DAILY_CLEANUP_TIME.split(":"))
    entry.async_on_unload(
        async_track_time_change(
            hass, _daily_cleanup, hour=hour, minute=minute, second=0
        )
    )

    # First-run bootstrap: without monitored_entities.json the capture is
    # idle and the file would only appear at the next 09:00 Wake. Run the
    # discovery now (after HA is fully started, so states are populated).
    monitored_path = hass.config.path(MONITORED_ENTITIES_RELATIVE_PATH)
    has_monitored = await hass.async_add_executor_job(
        os.path.exists, monitored_path
    )
    if not has_monitored:
        async def _first_wake(_hass) -> None:
            try:
                await wake.async_run()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("First-run Wake discovery failed")

        entry.async_on_unload(async_at_started(hass, _first_wake))

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "storage": storage,
        "capture": capture,
        "heartbeat": heartbeat,
        "sleep": sleep,
        "systems": systems,
        "wake": wake,
        "error_monitor": error_monitor,
        "updates": updates,
        "telegram": telegram,
        "config": config,
    }

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Options saved → reload the entry so every cycle re-reads the config."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """v1 (empty pre-v9.0 entry) → v2. NOT a permear.yaml migration — the old
    entry carried no data, so there is nothing to carry over. The integration
    loads with defaults (providers unset, honest errors); remove and re-add it
    through the UI to configure the providers."""
    if entry.version > 2:
        # Entry written by a newer PERMEAR — refuse to load after a downgrade
        return False
    if entry.version == 1:
        hass.config_entries.async_update_entry(entry, version=2)
        _LOGGER.warning(
            "PERMEAR entry migrated to v2 with no providers configured — "
            "remove and re-add the integration to set them up"
        )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload platforms; subsystem stops run via entry.async_on_unload."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
