"""PERMEAR config snapshot — built from the config entry (v9.0).

The config entry is the ONLY config source: data = install-time fields
(config_flow: providers + Telegram chat_id), options = adjustable fields
(options_flow: sensitivity, primary_resident, cycle schedules). The old
/config/permear.yaml is abandoned — never read, no migration (prototype
contract: the PM reconfigures once in the UI).

The frozen dataclass is the stable interface the consumers (heartbeat, sleep,
systems, wake, llm, sensor) already use — only the source changed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry

from .const import (
    CONF_AGENT_NAME,
    CONF_CHAT_ID,
    CONF_CONVERSATION,
    CONF_CONVERSATION_FALLBACK,
    CONF_DATA,
    CONF_DATA_FALLBACK,
    CONF_HEARTBEAT_END,
    CONF_HEARTBEAT_START,
    CONF_PRIMARY_RESIDENT,
    CONF_SENSITIVITY,
    CONF_SLEEP_TIME,
    CONF_SYSTEMS_TIME,
    CONF_VOICE_SCRIPT,
    DEFAULT_CHAT_ID,
    DEFAULT_HEARTBEAT_END,
    DEFAULT_HEARTBEAT_START,
    DEFAULT_SENSITIVITY,
    DEFAULT_SLEEP_TIME,
    DEFAULT_SYSTEMS_TIME,
    SENSITIVITY_MAP,
)

_LOGGER = logging.getLogger(__name__)


def parse_hhmm(value: str, default: str) -> tuple[int, int]:
    """'HH:MM' → (hour, minute), falling back to the given default."""
    for candidate in (value, default):
        try:
            hour_s, minute_s = candidate.split(":")[:2]
            hour, minute = int(hour_s), int(minute_s)
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return hour, minute
        except (ValueError, AttributeError):
            continue
    return 0, 0


def _hhmm(value, default: str) -> str:
    """Normalize a time field to 'HH:MM' (TimeSelector returns 'HH:MM:SS')."""
    if not isinstance(value, str) or not value.strip():
        return default
    hour, minute = parse_hhmm(value.strip(), default)
    return f"{hour:02d}:{minute:02d}"


@dataclass(frozen=True)
class PermearConfig:
    """Snapshot of the config entry at setup time."""

    conversation: str | None
    data: str | None
    conversation_fallback: str | None
    data_fallback: str | None
    primary_resident: str
    sensitivity: str
    threshold_min: int
    threshold_max: int
    heartbeat_start: str
    heartbeat_end: str
    sleep_time: str
    systems_time: str
    telegram_chat_id: str = DEFAULT_CHAT_ID
    # Brand-agnostic surface (v9.x): the agent's user-facing name (empty →
    # DEFAULT_AGENT_NAME at use) and an optional user voice hook (a service id
    # like "script.minha_voz"; empty → PERMEAR stays silent on voice).
    agent_name: str = ""
    voice_script: str = ""


def config_from_entry(entry: ConfigEntry) -> PermearConfig:
    """Config entry → typed snapshot. options override data; missing fields
    fall back to const.py defaults. threshold_min/max stay DERIVED from
    sensitivity (never stored, never user-tunable)."""
    data = entry.data
    options = entry.options
    merged = {**data, **options}

    # RODADA E: providers are reconfigurable in the options flow. options wins,
    # but an EMPTY options value falls back to data — a blank field means
    # "keep", never "clear" (must never zero a configured provider).
    def _provider(key: str) -> str | None:
        return (options.get(key) or data.get(key)) or None

    sensitivity = merged.get(CONF_SENSITIVITY, DEFAULT_SENSITIVITY)
    if sensitivity not in SENSITIVITY_MAP:
        _LOGGER.warning(
            "Unknown sensitivity %r — falling back to %s",
            sensitivity, DEFAULT_SENSITIVITY,
        )
        sensitivity = DEFAULT_SENSITIVITY
    threshold_min, threshold_max = SENSITIVITY_MAP[sensitivity]

    return PermearConfig(
        conversation=_provider(CONF_CONVERSATION),
        data=_provider(CONF_DATA),
        conversation_fallback=_provider(CONF_CONVERSATION_FALLBACK),
        data_fallback=_provider(CONF_DATA_FALLBACK),
        primary_resident=str(merged.get(CONF_PRIMARY_RESIDENT) or "").strip(),
        sensitivity=sensitivity,
        threshold_min=threshold_min,
        threshold_max=threshold_max,
        heartbeat_start=_hhmm(merged.get(CONF_HEARTBEAT_START), DEFAULT_HEARTBEAT_START),
        heartbeat_end=_hhmm(merged.get(CONF_HEARTBEAT_END), DEFAULT_HEARTBEAT_END),
        sleep_time=_hhmm(merged.get(CONF_SLEEP_TIME), DEFAULT_SLEEP_TIME),
        systems_time=_hhmm(merged.get(CONF_SYSTEMS_TIME), DEFAULT_SYSTEMS_TIME),
        telegram_chat_id=str(merged.get(CONF_CHAT_ID) or "").strip(),
        agent_name=str(merged.get(CONF_AGENT_NAME) or "").strip(),
        voice_script=str(merged.get(CONF_VOICE_SCRIPT) or "").strip(),
    )
