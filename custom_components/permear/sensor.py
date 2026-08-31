"""Native PERMEAR status sensors (v8.9) — replace the command_line sensors.

Five entities, same object_ids, states and attributes as the shell versions
(consumers in cycles.yaml/telegram.yaml read them via state_attr):

  sensor.permear_attention      — suppression rate % + ARAS daily stats
  sensor.permear_health         — tudo_ok | fallback_ativo | percepcao_reduzida (PT)
  sensor.permear_config         — providers + cycle schedules from permear.yaml
  sensor.permear_daily_memory   — today's events/interactions/flags from the DB
  sensor.permear_household_data — residents (HA persons) + action_items (DB)

All file/DB reads run in the executor. Polling every 5 minutes (the config
sensor is an in-memory snapshot and effectively static until reload).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .config import PermearConfig
from .const import (
    AGENT_CIRCUIT_RELATIVE_PATH,
    ARAS_STATS_RELATIVE_PATH,
    ARCHIVED_ERRORS_RELATIVE_PATH,
    AVAILABILITY_RELATIVE_PATH,
    DOMAIN,
    HEALTH_FALLBACK_WINDOW_MINUTES,
    MONITORED_ENTITIES_RELATIVE_PATH,
    PERCEPTION_MIN_ENTITIES,
    PERCEPTION_SILENT_MIN_HOURS,
    PERCEPTION_SILENT_SHARE,
)
from .household import get_residents
from .storage import PermearStorage, load_json

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=5)

# Recorder caps state attributes at 16 KiB — the daily event list must be
# bounded (busy days blew the limit every 5 minutes).
DAILY_MEMORY_MAX_EVENTS = 20


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    storage: PermearStorage = data["storage"]
    config: PermearConfig = data["config"]
    async_add_entities(
        [
            PermearAttentionSensor(hass),
            PermearHealthSensor(hass),
            PermearConfigSensor(config),
            PermearDailyMemorySensor(storage),
            PermearHouseholdDataSensor(hass, storage),
        ],
        update_before_add=True,
    )


class PermearSensorBase(SensorEntity):
    """Common identity plumbing. Explicit entity_id keeps the production
    object_ids the YAML consumers expect (post-cutover)."""

    _attr_should_poll = True
    _attr_has_entity_name = True
    _attr_device_info = DeviceInfo(
        identifiers={(DOMAIN, DOMAIN)},
        name="PERMEAR",
        entry_type=DeviceEntryType.SERVICE,
    )

    def __init__(self, key: str, name: str) -> None:
        self._attr_unique_id = f"{DOMAIN}_{key}"
        self._attr_name = name
        self.entity_id = f"sensor.{DOMAIN}_{key}"


class PermearAttentionSensor(PermearSensorBase):
    """Suppression rate (%) — how much the ARAS is filtering today."""

    _attr_native_unit_of_measurement = "%"

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__("attention", "Attention")
        self._attr_icon = "mdi:brain"
        self._hass = hass

    async def async_update(self) -> None:
        stats = await self._hass.async_add_executor_job(
            load_json, self._hass.config.path(ARAS_STATS_RELATIVE_PATH), {}
        )
        today = datetime.now().strftime("%Y-%m-%d")
        if stats.get("data") != today:
            stats = {"total": 0, "emit": 0, "gray": 0,
                     "suppress": 0, "llm_calls": 0}
        total = stats.get("total", 0)
        suppress = stats.get("suppress", 0)
        self._attr_native_value = round(100 * suppress / total, 1) if total else 0.0
        self._attr_extra_state_attributes = {
            "emitidos_hoje": stats.get("emit", 0),
            "suprimidos_hoje": suppress,
            "cinzentos_hoje": stats.get("gray", 0),
            "chamadas_llm_hoje": stats.get("llm_calls", 0),
            "total_avaliado_hoje": total,
            # v9.7.2 — gray replies discarded as "nothing to say" written in
            # prose. Surfaced so the widening of that judgement stays visible:
            # a detector that swallows real alerts would show up here first.
            "nao_mensagens_hoje": stats.get("non_messages", 0),
            "threshold_emit_atual": stats.get("emit_threshold"),
        }


class PermearHealthSensor(PermearSensorBase):
    """tudo_ok | fallback_ativo | percepcao_reduzida (user-facing PT).
    The live fallback signal stays agent_circuit.json.last_fallback_at.

    percepcao_reduzida (v9.5): availability is global health, never an event
    (rule #8) — in 2026-07 the sensory periphery was down for ~10 days and this
    sensor read tudo_ok throughout. When most monitored entities have been
    silent for hours, the gravest fact about the system is that it is blind,
    so that state outranks fallback_ativo. Deterministic, from the existing
    availability snapshot; nothing is emitted to the resident."""

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__("health", "Health")
        self._attr_icon = "mdi:heart-pulse"
        self._hass = hass

    async def async_update(self) -> None:
        circuit, archived, perception = await self._hass.async_add_executor_job(
            self._read
        )
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        raw_stats = circuit.get("daily_stats") or {}
        stats = raw_stats if raw_stats.get("date") == today else {}
        # "fallbacks_gemini" is the pre-v9.0 key — read both during transition
        fallbacks = stats.get("fallbacks", stats.get("fallbacks_gemini", 0))
        # RODADA D: state reflects the CURRENT situation, not "any fallback
        # today". fallback_ativo only while the last fallback is recent (we're
        # still on the secondary); once the window passes the primary is back.
        # fallbacks_hoje keeps being daily history (attribute only).
        last_fb = self._parse_local(circuit.get("last_fallback_at"))
        recent = (
            last_fb is not None
            and now - last_fb <= timedelta(minutes=HEALTH_FALLBACK_WINDOW_MINUTES)
        )
        silent_count, watched_count = perception
        if (
            watched_count >= PERCEPTION_MIN_ENTITIES
            and silent_count / watched_count >= PERCEPTION_SILENT_SHARE
        ):
            state = "percepcao_reduzida"
            resumo = (
                f"Percepcao reduzida: {silent_count} de {watched_count} "
                "entidades monitoradas sem responder ha mais de "
                f"{PERCEPTION_SILENT_MIN_HOURS}h."
            )
        elif recent:
            state = "fallback_ativo"
            resumo = "Operando com provedor secundario agora."
        else:
            state = "tudo_ok"
            resumo = "Funcionando normalmente"
        self._attr_native_value = state
        self._attr_extra_state_attributes = {
            "resumo": resumo,
            "fallbacks_hoje": fallbacks,
            "ultimo_fallback_em": circuit.get("last_fallback_at"),
            "erros_silenciados_ativos": len(archived.get("errors", {})),
            "entidades_silenciosas": silent_count,
            "entidades_monitoradas": watched_count,
        }

    @staticmethod
    def _parse_local(value) -> datetime | None:
        """Parse last_fallback_at (LOCAL, naive). Accepts both the space form
        '2026-06-15 09:26:28' and ISO 'T' with microseconds. Never raises."""
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except (ValueError, TypeError):
            return None

    def _read(self) -> tuple:
        circuit = load_json(
            self._hass.config.path(AGENT_CIRCUIT_RELATIVE_PATH), {}
        )
        archived = load_json(
            self._hass.config.path(ARCHIVED_ERRORS_RELATIVE_PATH), {"errors": {}}
        )
        return circuit, archived, self._perception_counts()

    def _perception_counts(self) -> tuple:
        """(silent, watched) over monitor=true entities present in the
        availability snapshot the Heartbeat already maintains. Silent = state
        unavailable/unknown for over PERCEPTION_SILENT_MIN_HOURS (the 'since'
        in the snapshot survives restarts). Entities the snapshot has never
        seen don't count — the denominator is what the system can vouch for.
        Gotcha: monitored entities live in the entities[] LIST, not dict keys."""
        snapshot = load_json(
            self._hass.config.path(AVAILABILITY_RELATIVE_PATH), {}
        )
        monitored = load_json(
            self._hass.config.path(MONITORED_ENTITIES_RELATIVE_PATH), {}
        )
        floor = datetime.now() - timedelta(hours=PERCEPTION_SILENT_MIN_HOURS)
        silent = watched = 0
        for ent in monitored.get("entities", []):
            if not ent.get("monitor"):
                continue
            info = snapshot.get(ent.get("entity_id"))
            if not isinstance(info, dict):
                continue
            watched += 1
            if info.get("last_state") != "silent":
                continue
            since = self._parse_local(info.get("since"))
            if since is not None and since <= floor:
                silent += 1
        return silent, watched


class PermearConfigSensor(PermearSensorBase):
    """Config entry snapshot exposed to YAML consumers. Static — no I/O."""

    def __init__(self, config: PermearConfig) -> None:
        super().__init__("config", "Config")
        self._attr_icon = "mdi:head-cog"
        self._config = config

    @staticmethod
    def _hms(t: str) -> str:
        return t + ":00" if len(t) == 5 else t

    async def async_update(self) -> None:
        cfg = self._config
        self._attr_native_value = "ok"
        self._attr_extra_state_attributes = {
            "conversation": cfg.conversation,
            "data": cfg.data,
            "conversation_fallback": cfg.conversation_fallback,
            "data_fallback": cfg.data_fallback,
            "heartbeat_start": self._hms(cfg.heartbeat_start),
            "heartbeat_end": self._hms(cfg.heartbeat_end),
            "sleep_time": self._hms(cfg.sleep_time),
            "systems_time": self._hms(cfg.systems_time),
        }


class PermearDailyMemorySensor(PermearSensorBase):
    """Today's events + interactions + daily flags, straight from the DB."""

    def __init__(self, storage: PermearStorage) -> None:
        super().__init__("daily_memory", "Daily Memory")
        self._attr_icon = "mdi:notebook-outline"
        self._storage = storage

    async def async_update(self) -> None:
        summary = await self._storage.async_daily_summary()
        eventos = summary["eventos"]
        self._attr_native_value = "ok"
        self._attr_extra_state_attributes = {
            "data": summary["data"],
            "total_eventos": len(eventos),
            "eventos": [
                {"ts": e.get("ts"), "entity_id": e.get("entity_id"),
                 "detalhe": e.get("detalhe")}
                for e in eventos[-DAILY_MEMORY_MAX_EVENTS:]
            ],
            "interacoes": summary["interacoes"][-DAILY_MEMORY_MAX_EVENTS:],
            "memorias_do_dia": [],
            "boletim_disparado": summary["boletim_disparado"],
            "briefing_enviado": summary["briefing_enviado"],
        }


class PermearHouseholdDataSensor(PermearSensorBase):
    """residents from the HA person registry (v9.0.1 — replaced
    guidelines.json) + action_items from the DB (source='systems')."""

    def __init__(self, hass: HomeAssistant, storage: PermearStorage) -> None:
        super().__init__("household_data", "Household Data")
        self._attr_icon = "mdi:home-heart"
        self._hass = hass
        self._storage = storage

    async def async_update(self) -> None:
        insights = await self._storage.async_system_insights()
        self._attr_native_value = "ok"
        self._attr_extra_state_attributes = {
            "residents": get_residents(self._hass),
            "action_items": insights,
        }
