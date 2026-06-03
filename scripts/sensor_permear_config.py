#!/usr/bin/env python3
"""
Exposes permear.yaml settings as sensor attributes so YAML automations
can read them via state_attr('sensor.permear_config', 'xxx').
Single source: permear.yaml. No dual-maintenance anywhere.

Attributes exposed:
  Providers:  conversation, data, conversation_fallback, data_fallback
  Schedules:  heartbeat_start, heartbeat_end, sleep_time, systems_time
              (in HH:MM:SS format for input_datetime.set_datetime)
"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import (
    CONVERSATION_PROVIDER, DATA_PROVIDER,
    CONVERSATION_FALLBACK, DATA_FALLBACK,
    CYCLES_HEARTBEAT_START, CYCLES_HEARTBEAT_END,
    CYCLES_SLEEP_TIME, CYCLES_SYSTEMS_TIME,
)


def _hms(t):
    """Ensure time string is HH:MM:SS (pad :00 if only HH:MM)."""
    return t + ":00" if len(t) == 5 else t


print(json.dumps({
    "state": "ok",
    "conversation":          CONVERSATION_PROVIDER,
    "data":                  DATA_PROVIDER,
    "conversation_fallback": CONVERSATION_FALLBACK,
    "data_fallback":         DATA_FALLBACK,
    "heartbeat_start":       _hms(CYCLES_HEARTBEAT_START),
    "heartbeat_end":         _hms(CYCLES_HEARTBEAT_END),
    "sleep_time":            _hms(CYCLES_SLEEP_TIME),
    "systems_time":          _hms(CYCLES_SYSTEMS_TIME),
}))
