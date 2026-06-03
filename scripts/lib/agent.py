"""
v7.1-H — Circuit breaker + health helpers for LLM agent calls.

conversation.process (interactive Telegram + voice) handled by YAML retry.
ai_task.generate_data (non-interactive cycles) handled natively by HA.
"""
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from permear_config import AGENT_CIRCUIT_PATH, ARCHIVED_ERRORS_PATH
from lib.memory import load_json, save_json, parse_iso, locked_update

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
    """Non-critical read (no lock) — for read-only functions."""
    return load_json(STATE_PATH, default=dict(_DEFAULT_STATE))


def reset_daily_if_needed(state):
    """Reset daily counters if the date changed."""
    today = datetime.now().strftime("%Y-%m-%d")
    stats = state.get("daily_stats", {})
    if stats.get("date") != today:
        state["daily_stats"] = {
            "date": today,
            "errors_503_seen": 0,
            "retries_recovered": 0,
            "failures_3x": 0,
            "circuit_opens": 0,
            "fallbacks_gemini": 0,  # v7.1-I
        }
    return state


def cmd_check():
    state = load_state()
    open_until = parse_iso(state.get("circuit_open_until"))
    if open_until and datetime.now() < open_until:
        remaining = (open_until - datetime.now()).total_seconds()
        print(f"COOLDOWN: {int(remaining)}")
        return
    print("OK")


def cmd_fail():
    # v7.3-B.2 — locked_update
    with locked_update(STATE_PATH, default=dict(_DEFAULT_STATE)) as state:
        now = datetime.now()
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
            reset_daily_if_needed(state)
            state["daily_stats"]["circuit_opens"] += 1
            print(f"CIRCUIT_OPEN: ate {open_until.strftime('%H:%M')} ({COOLDOWN_MINUTES} min)")
            return  # exits the with -> locked_update saves

        print(f"FAIL_COUNT: {state['consecutive_failures']}/{FAILURE_THRESHOLD}")


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
        reset_daily_if_needed(state)
        state["daily_stats"]["errors_503_seen"] += 1
    print("OK")


def cmd_log_retry_success():
    with locked_update(STATE_PATH, default=dict(_DEFAULT_STATE)) as state:
        reset_daily_if_needed(state)
        state["daily_stats"]["retries_recovered"] += 1
    print("OK")


def cmd_log_3fail():
    with locked_update(STATE_PATH, default=dict(_DEFAULT_STATE)) as state:
        reset_daily_if_needed(state)
        state["daily_stats"]["failures_3x"] += 1
    print("OK")


def cmd_daily_summary():
    """PT-BR summary for the briefing. Prints empty if zero activity."""
    state = load_state()
    state = reset_daily_if_needed(state)
    stats = state["daily_stats"]
    total = (stats.get("errors_503_seen", 0)
             + stats.get("failures_3x", 0)
             + stats.get("circuit_opens", 0))
    if total == 0:
        print("")
        return
    lines = ["", "Saude do agente hoje:"]
    if stats.get("errors_503_seen", 0):
        lines.append(f"- {stats['errors_503_seen']} erros 503 observados")
    if stats.get("retries_recovered", 0):
        lines.append(f"- {stats['retries_recovered']} retries recuperaram automaticamente")
    if stats.get("failures_3x", 0):
        lines.append(f"- {stats['failures_3x']} falhas apos 3 tentativas")
    if stats.get("circuit_opens", 0):
        lines.append(f"- {stats['circuit_opens']} aberturas do circuit breaker")
    print("\n".join(lines))


def increment_fallback_count():
    """Increment the fallback counter for the secondary Gemini. v7.1-I / v7.3-B.2"""
    with locked_update(STATE_PATH, default=dict(_DEFAULT_STATE)) as state:
        reset_daily_if_needed(state)
        state["daily_stats"]["fallbacks_gemini"] = state["daily_stats"].get("fallbacks_gemini", 0) + 1
        state["last_fallback_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        count = state["daily_stats"]["fallbacks_gemini"]
    return count


def get_health_summary_for_prompt():
    """
    Return a 1-line PT-BR description of system health to include in
    briefing/pre-briefing prompts. Returns an empty string if all OK.
    """
    state = load_state()
    state = reset_daily_if_needed(state)
    stats = state.get("daily_stats", {})

    archived = load_json(ARCHIVED_ERRORS_PATH, default={"errors": {}})
    archived_count = len(archived.get("errors", {}))

    open_until = parse_iso(state.get("circuit_open_until"))
    circuit_open = bool(open_until and datetime.now() < open_until)

    failures = stats.get("failures_3x", 0)
    retries_ok = stats.get("retries_recovered", 0)

    if circuit_open:
        return f"Saúde: circuit breaker aberto até {open_until.strftime('%H:%M')}, sistema degradado."
    if failures >= 2:
        return f"Saúde: {failures} falhas finais hoje após retries — atenção."
    if archived_count >= 5:
        return f"Saúde: {archived_count} erros silenciados ativos."
    if retries_ok >= 2:
        return f"Saúde: agente recuperou de {retries_ok} hiccups hoje via retry."

    return ""
