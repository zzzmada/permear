"""
v7.1-H — Circuit breaker + health helpers for LLM agent calls.
v7.3-B.2 — Mutating functions migrated to locked_update (atomic read-modify-write).

conversation.process (interactive Telegram + voice) managed by YAML retry.
ai_task.generate_data (non-interactive cycles) managed natively by HA.
"""
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from permear_config import AGENT_CIRCUIT_PATH, ARCHIVED_ERRORS_PATH
from lib.memory import load_json, locked_update, parse_iso

STATE_PATH = AGENT_CIRCUIT_PATH
FAILURE_THRESHOLD = 3
COOLDOWN_MINUTES = 10
WINDOW_MINUTES = 5

_DEFAULT_STATE = {
    "consecutive_failures": 0,
    "last_failure_at": None,
    "circuit_open_until": None,
    "total_opens": 0,
    "last_success_at": None,
}


def load_state():
    """Read-only access to circuit state."""
    return load_json(STATE_PATH, default=dict(_DEFAULT_STATE))


def _reset_daily_inplace(state):
    """Reset daily counters if date changed. Mutates state dict in place."""
    today = datetime.now().strftime("%Y-%m-%d")
    stats = state.get("daily_stats", {})
    if stats.get("date") != today:
        state["daily_stats"] = {
            "date": today,
            "errors_503_seen": 0,
            "retries_recovered": 0,
            "failures_3x": 0,
            "circuit_opens": 0,
            "fallbacks_secondary": 0,
        }


def cmd_check():
    state = load_state()
    open_until = parse_iso(state.get("circuit_open_until"))
    if open_until and datetime.now() < open_until:
        remaining = (open_until - datetime.now()).total_seconds()
        print(f"COOLDOWN: {int(remaining)}")
        return
    print("OK")


def cmd_fail():
    now = datetime.now()
    with locked_update(STATE_PATH, default=dict(_DEFAULT_STATE)) as state:
        last_fail = parse_iso(state.get("last_failure_at"))
        if last_fail and (now - last_fail) > timedelta(minutes=WINDOW_MINUTES):
            state["consecutive_failures"] = 0

        state["consecutive_failures"] += 1
        state["last_failure_at"] = now.isoformat()

        if state["consecutive_failures"] >= FAILURE_THRESHOLD:
            open_until = now + timedelta(minutes=COOLDOWN_MINUTES)
            state["circuit_open_until"] = open_until.isoformat()
            state["total_opens"] = state.get("total_opens", 0) + 1
            state["consecutive_failures"] = 0
            _reset_daily_inplace(state)
            state["daily_stats"]["circuit_opens"] += 1
            print(f"CIRCUIT_OPEN: until {open_until.strftime('%H:%M')} ({COOLDOWN_MINUTES} min)")
            return
    print(f"FAIL_COUNT recorded")


def cmd_success():
    with locked_update(STATE_PATH, default=dict(_DEFAULT_STATE)) as state:
        state["consecutive_failures"] = 0
        state["last_success_at"] = datetime.now().isoformat()
        state["circuit_open_until"] = None
    print("OK")


def cmd_status():
    import json
    state = load_state()
    print(json.dumps(state, indent=2, ensure_ascii=False))


def cmd_log_503():
    with locked_update(STATE_PATH, default=dict(_DEFAULT_STATE)) as state:
        _reset_daily_inplace(state)
        state["daily_stats"]["errors_503_seen"] += 1
    print("OK")


def cmd_log_retry_success():
    with locked_update(STATE_PATH, default=dict(_DEFAULT_STATE)) as state:
        _reset_daily_inplace(state)
        state["daily_stats"]["retries_recovered"] += 1
    print("OK")


def cmd_log_3fail():
    with locked_update(STATE_PATH, default=dict(_DEFAULT_STATE)) as state:
        _reset_daily_inplace(state)
        state["daily_stats"]["failures_3x"] += 1
    print("OK")


def cmd_daily_summary():
    state = load_state()
    # Compute summary from snapshot
    today = datetime.now().strftime("%Y-%m-%d")
    raw_stats = state.get("daily_stats", {})
    stats = raw_stats if raw_stats.get("date") == today else {}

    total = (stats.get("errors_503_seen", 0)
             + stats.get("failures_3x", 0)
             + stats.get("circuit_opens", 0))
    if total == 0:
        print("")
        return
    lines = ["", "Agent health today:"]
    if stats.get("errors_503_seen", 0):
        lines.append(f"- {stats['errors_503_seen']} transient errors observed")
    if stats.get("retries_recovered", 0):
        lines.append(f"- {stats['retries_recovered']} retries auto-recovered")
    if stats.get("failures_3x", 0):
        lines.append(f"- {stats['failures_3x']} failures after 3 retries")
    if stats.get("circuit_opens", 0):
        lines.append(f"- {stats['circuit_opens']} circuit breaker opens")
    print("\n".join(lines))


def increment_fallback_count():
    """v7.1-I — Increment fallback counter for secondary provider."""
    count = 0
    with locked_update(STATE_PATH, default=dict(_DEFAULT_STATE)) as state:
        _reset_daily_inplace(state)
        state["daily_stats"]["fallbacks_secondary"] = state["daily_stats"].get("fallbacks_secondary", 0) + 1
        state["last_fallback_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        count = state["daily_stats"]["fallbacks_secondary"]
    return count


def get_health_summary_for_prompt():
    """Returns 1-line description of system health for briefing prompts."""
    state = load_state()
    today = datetime.now().strftime("%Y-%m-%d")
    raw_stats = state.get("daily_stats", {})
    stats = raw_stats if raw_stats.get("date") == today else {}

    archived = load_json(ARCHIVED_ERRORS_PATH, default={"errors": {}})
    archived_count = len(archived.get("errors", {}))

    open_until = parse_iso(state.get("circuit_open_until"))
    circuit_open = bool(open_until and datetime.now() < open_until)

    failures = stats.get("failures_3x", 0)
    retries_ok = stats.get("retries_recovered", 0)

    if circuit_open:
        return f"Health: circuit breaker open until {open_until.strftime('%H:%M')}, system degraded."
    if failures >= 2:
        return f"Health: {failures} final failures today after retries — attention."
    if archived_count >= 5:
        return f"Health: {archived_count} silenced errors active."
    if retries_ok >= 2:
        return f"Health: agent recovered from {retries_ok} hiccups today via retry."

    return ""
