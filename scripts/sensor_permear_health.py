#!/usr/bin/env python3
"""
v7.1-I — PERMEAR health sensor with English states.

States (priority order):
  degraded:        circuit open OR multiple final failures today
  fallback_active: secondary AI Task provider used today (v7.1-I)
  recovering:      had failures but retry recovered
  all_ok:          working without retries today
"""
import sys
import os
import json
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.memory import load_json, parse_iso
from permear_config import AGENT_CIRCUIT_PATH, ARCHIVED_ERRORS_PATH


def _format_circuit_state(circuit):
    open_until = parse_iso(circuit.get("circuit_open_until"))
    if open_until and datetime.now() < open_until:
        return f"open until {open_until.strftime('%H:%M')}"
    return "closed"


def _determine_state_and_summary(circuit, archived):
    """Determine state and summary phrase. Priority: degraded > fallback_active > recovering > all_ok."""
    stats = circuit.get("daily_stats", {})
    failures = stats.get("failures_3x", 0)
    retries_ok = stats.get("retries_recovered", 0)
    fallbacks = stats.get("fallbacks_secondary", 0)
    archived_count = len(archived.get("errors", {}))

    open_until = parse_iso(circuit.get("circuit_open_until"))
    circuit_now_open = bool(open_until and datetime.now() < open_until)

    if circuit_now_open:
        return "degraded", f"Circuit breaker open until {open_until.strftime('%H:%M')}"
    if failures >= 2:
        return "degraded", f"{failures} final failures today after retries"
    if archived_count >= 5:
        return "degraded", f"{archived_count} active silenced errors (high)"

    if fallbacks >= 1:
        return "fallback_active", f"Secondary provider used {fallbacks}x today"

    if retries_ok >= 1:
        return "recovering", f"Agent recovered from {retries_ok} hiccup(s) via retry"
    if failures == 1:
        return "recovering", "1 failure today but stabilized"

    return "all_ok", "Working normally"


def main():
    circuit = load_json(AGENT_CIRCUIT_PATH, default={
        "consecutive_failures": 0,
        "circuit_open_until": None,
        "daily_stats": {},
        "last_success_at": None,
        "last_failure_at": None,
    })
    archived = load_json(ARCHIVED_ERRORS_PATH, default={"errors": {}})

    # If daily_stats is from another day, read as zeros (sensor is read-only, doesn't write)
    today = datetime.now().strftime("%Y-%m-%d")
    raw_stats = circuit.get("daily_stats", {})
    stats = raw_stats if raw_stats.get("date") == today else {}
    circuit_view = dict(circuit)
    circuit_view["daily_stats"] = stats
    state, summary = _determine_state_and_summary(circuit_view, archived)

    out = {
        "state": state,
        "summary": summary,
        "retries_recovered_today": stats.get("retries_recovered", 0),
        "final_failures_today": stats.get("failures_3x", 0),
        "circuit_status": _format_circuit_state(circuit),
        "active_silenced_errors": len(archived.get("errors", {})),
        "last_failure_at": circuit.get("last_failure_at"),
        "last_success_at": circuit.get("last_success_at"),
        "fallbacks_secondary_today": stats.get("fallbacks_secondary", 0),
        "last_fallback_at": circuit.get("last_fallback_at"),
    }

    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
