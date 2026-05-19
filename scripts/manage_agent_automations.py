#!/usr/bin/env python3
"""
CRUD for agent-managed automations in agent_automations.yaml.
v7.1-B: JSON output mode, new commands (details, disable, enable, stats).
v7.3-C: validate_ha_config before reload (rollback if invalid).
v7.3-C: fix_json returns tuple (parsed, needed_repair) for circuit breaker tracking.

Usage:
  manage_agent_automations.py list [--json]
  manage_agent_automations.py create '<json_automation>' [--json]
  manage_agent_automations.py create_from_file [--json]
  manage_agent_automations.py remove '<alias_or_id>' [--json]
  manage_agent_automations.py details '<alias_or_id>' [--json]
  manage_agent_automations.py disable '<alias_or_id>' [--json]
  manage_agent_automations.py enable '<alias_or_id>' [--json]
  manage_agent_automations.py stats [--json]
"""
import json
import re
import sys
import os
import time
import subprocess
import yaml
from urllib.request import Request, urlopen
from urllib.error import URLError
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import *
from lib.memory import load_yaml, save_yaml


# ==============================================================================
# Utility helpers
# ==============================================================================

def parse_json_flag(args):
    json_mode = "--json" in args
    clean_args = [a for a in args if a != "--json"]
    return json_mode, clean_args


def emit_json(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


def fix_json(raw):
    """
    v7.3-C — Returns tuple (parsed, needed_repair: bool).
    needed_repair=True signals provider degradation (inferential).
    """
    if not raw or not raw.strip():
        return None, False

    # Try pure parse first
    try:
        return json.loads(raw), False
    except json.JSONDecodeError:
        pass

    needed_repair = True
    text = re.sub(r'```(?:json)?\s*', '', raw).strip().rstrip('`').strip()
    try:
        return json.loads(text), needed_repair
    except json.JSONDecodeError:
        pass
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        candidate = m.group(0)
        try:
            return json.loads(candidate), needed_repair
        except json.JSONDecodeError:
            pass
        candidate = re.sub(r',\s*([}\]])', r'\1', candidate)
        try:
            return json.loads(candidate), needed_repair
        except json.JSONDecodeError:
            pass
        candidate = candidate.replace("'", '"')
        try:
            return json.loads(candidate), needed_repair
        except json.JSONDecodeError:
            pass
    return None, needed_repair


def log_inferential_degradation():
    """v7.3-C — fire-and-forget log to circuit breaker when fix_json had to repair."""
    try:
        subprocess.run(
            ["python3", "/config/scripts/circuit_breaker.py", "log_503"],
            capture_output=True, timeout=3
        )
    except Exception:
        pass


# ==============================================================================
# HA infrastructure
# ==============================================================================

def load_token():
    try:
        with open(TOKEN_PATH, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


def ha_api(endpoint, method="GET", data=None, token=None):
    url = f"{HA_URL}/api/{endpoint}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = json.dumps(data).encode() if data else None
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except URLError as e:
        print(f"HA API error: {e}")
        return None


def entity_exists(entity_id, token):
    result = ha_api(f"states/{entity_id}", token=token)
    return result is not None


def reload_automations(token):
    result = ha_api("services/automation/reload", method="POST", token=token)
    return result is not None


def validate_ha_config(token):
    """
    v7.3-C — Call Supervisor API to validate HA config before reload.
    Returns (ok: bool, error_message: str).
    Outside HAOS container (no SUPERVISOR_TOKEN): returns (True, "") for backward compat.
    """
    supervisor_token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not supervisor_token:
        return True, ""

    url = "http://supervisor/core/api/config/core/check_config"
    headers = {"Authorization": f"Bearer {supervisor_token}", "Content-Type": "application/json"}
    req = Request(url, method="POST", headers=headers)

    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        result = data.get("result", "unknown")
        if result == "valid":
            return True, ""
        else:
            errors = data.get("errors") or "config check failed"
            return False, str(errors)[:500]
    except (URLError, json.JSONDecodeError) as e:
        print(f"WARNING: validate_ha_config failed ({e}), skipping check", file=sys.stderr)
        return True, ""


# ==============================================================================
# Automation I/O
# ==============================================================================

def save_automations(automations):
    """Save and validate YAML syntax. Returns True if OK."""
    save_yaml(AGENT_YAML, automations)
    try:
        with open(AGENT_YAML, 'r') as f:
            yaml.safe_load(f)
        return True
    except yaml.YAMLError as e:
        print(f"ERROR: Written YAML is invalid: {e}")
        return False


# ==============================================================================
# Summary helpers
# ==============================================================================

def _find_automation(automations, identifier):
    identifier_lower = identifier.strip().lower()
    for a in automations:
        if a.get("id", "").lower() == identifier_lower or \
           a.get("alias", "").lower() == identifier_lower:
            return a
    return None


def _summarize_trigger(triggers):
    if not triggers:
        return "no trigger"
    if not isinstance(triggers, list):
        triggers = [triggers]
    t = triggers[0]
    platform = t.get("platform", "?")
    if platform == "time":
        return f"every day at {t.get('at', '?')}"
    if platform == "state":
        entity = t.get("entity_id", "?")
        to = t.get("to")
        return f"{entity} change to {to}" if to else f"{entity} state change"
    if platform == "numeric_state":
        entity = t.get("entity_id", "?")
        above = t.get("above")
        below = t.get("below")
        if above is not None:
            return f"{entity} above {above}"
        if below is not None:
            return f"{entity} below {below}"
        return f"{entity} (numeric value)"
    if platform == "time_pattern":
        return "recurring time pattern"
    if platform == "event":
        return f"event {t.get('event_type', '?')}"
    return f"trigger {platform}"


def _summarize_action(actions):
    if not actions:
        return "no action"
    if not isinstance(actions, list):
        actions = [actions]
    a = actions[0]
    service = a.get("service", a.get("action", "?"))
    target = a.get("target", {}).get("entity_id", a.get("entity_id", ""))
    return f"{service} on {target}" if target else service


# ==============================================================================
# Commands - list and details
# ==============================================================================

def cmd_list(json_mode=False):
    automations = load_yaml(AGENT_YAML, default=[])
    if json_mode:
        items = []
        for a in automations:
            items.append({
                "id": a.get("id", ""),
                "alias": a.get("alias", "unnamed"),
                "enabled": a.get("initial_state", "on") == "on",
                "trigger_summary": _summarize_trigger(a.get("trigger", [])),
            })
        emit_json({"count": len(items), "automations": items})
        return
    if not automations:
        print("No automations created yet.")
        return
    lines = [f"Active automations ({len(automations)}):"]
    for i, a in enumerate(automations, 1):
        alias = a.get("alias", "?")
        triggers = len(a.get("trigger", []))
        actions = len(a.get("action", []))
        lines.append(f"{i}. {alias} ({triggers} trigger, {actions} action)")
    print("\n".join(lines))


def cmd_details(identifier, json_mode=False):
    automations = load_yaml(AGENT_YAML, default=[])
    auto = _find_automation(automations, identifier)
    if not auto:
        if json_mode:
            emit_json({"success": False, "error": f"Automation '{identifier}' not found"})
        else:
            print(f"Automation '{identifier}' not found.")
        return
    if json_mode:
        emit_json({
            "success": True,
            "id": auto.get("id", ""),
            "alias": auto.get("alias", ""),
            "enabled": auto.get("initial_state", "on") == "on",
            "trigger": auto.get("trigger", []),
            "trigger_summary": _summarize_trigger(auto.get("trigger", [])),
            "action": auto.get("action", []),
            "action_summary": _summarize_action(auto.get("action", [])),
            "condition": auto.get("condition", []),
            "mode": auto.get("mode", "single"),
        })
        return
    print(f"Automation: {auto.get('alias', 'unnamed')}")
    print(f"  ID: {auto.get('id', '?')}")
    print(f"  Status: {'active' if auto.get('initial_state', 'on') == 'on' else 'disabled'}")
    print(f"  Trigger: {_summarize_trigger(auto.get('trigger', []))}")
    print(f"  Action: {_summarize_action(auto.get('action', []))}")


def cmd_stats(json_mode=False):
    automations = load_yaml(AGENT_YAML, default=[])
    total = len(automations)
    active = sum(1 for a in automations if a.get("initial_state", "on") == "on")
    disabled = total - active
    triggers_by_type = {}
    for a in automations:
        triggers = a.get("trigger", [])
        if not isinstance(triggers, list):
            triggers = [triggers]
        for t in triggers:
            tp = t.get("platform", "unknown")
            triggers_by_type[tp] = triggers_by_type.get(tp, 0) + 1
    if json_mode:
        emit_json({
            "total": total,
            "active": active,
            "disabled": disabled,
            "triggers_by_type": triggers_by_type,
        })
        return
    print(f"Total agent automations: {total}")
    print(f"  Active: {active}")
    print(f"  Disabled: {disabled}")
    if triggers_by_type:
        print("  Trigger types:")
        for tp, count in sorted(triggers_by_type.items()):
            print(f"    - {tp}: {count}")


# ==============================================================================
# Commands - create / remove (with validate-before-reload)
# ==============================================================================

def cmd_create(json_str, token, json_mode=False):
    if not json_str or not json_str.strip():
        if json_mode:
            emit_json({"success": False, "error": "empty JSON spec"})
        else:
            print("ERROR: Empty spec.")
        return

    # v7.3-C — fix_json returns tuple
    spec, needed_repair = fix_json(json_str)
    if needed_repair:
        log_inferential_degradation()

    if spec is None:
        if json_mode:
            emit_json({"success": False, "error": "invalid JSON and could not auto-correct"})
        else:
            print("ERROR: Invalid JSON and could not auto-correct.")
        return

    alias = spec.get("alias", "").strip()
    if not alias:
        if json_mode:
            emit_json({"success": False, "error": "'alias' is required"})
        else:
            print("ERROR: 'alias' is required.")
        return

    auto_id = spec.get("id") or f"agent_auto_{int(time.time())}"

    trigger = spec.get("trigger")
    if not trigger:
        if json_mode:
            emit_json({"success": False, "error": "'trigger' is required"})
        else:
            print("ERROR: 'trigger' is required.")
        return

    def infer_platform(t):
        if "platform" in t:
            return t
        if "at" in t:
            t["platform"] = "time"
        elif "above" in t or "below" in t:
            t["platform"] = "numeric_state"
        elif "entity_id" in t:
            t["platform"] = "state"
        return t

    if isinstance(trigger, list):
        trigger = [infer_platform(t) for t in trigger]
        for t in trigger:
            eid = t.get("entity_id")
            if eid and not entity_exists(eid, token):
                if json_mode:
                    emit_json({"success": False, "error": f"Entity '{eid}' does not exist in HA"})
                else:
                    print(f"ERROR: Entity '{eid}' does not exist in HA.")
                return
    elif isinstance(trigger, dict):
        trigger = infer_platform(trigger)
        eid = trigger.get("entity_id")
        if eid and not entity_exists(eid, token):
            if json_mode:
                emit_json({"success": False, "error": f"Entity '{eid}' does not exist in HA"})
            else:
                print(f"ERROR: Entity '{eid}' does not exist in HA.")
            return
        trigger = [trigger]

    action = spec.get("action")
    if not action:
        if json_mode:
            emit_json({"success": False, "error": "'action' is required"})
        else:
            print("ERROR: 'action' is required.")
        return
    if isinstance(action, dict):
        action = [action]

    for a in action:
        if "action" in a and "service" not in a:
            a["service"] = a.pop("action")

    for a in action:
        if "data" in a and "entity_id" in a["data"]:
            eid = a["data"]["entity_id"]
            if not entity_exists(eid, token):
                if json_mode:
                    emit_json({"success": False, "error": f"Entity '{eid}' in action does not exist"})
                else:
                    print(f"ERROR: Entity '{eid}' in action does not exist.")
                return
        if "target" in a and "entity_id" in a["target"]:
            eid = a["target"]["entity_id"]
            if not entity_exists(eid, token):
                if json_mode:
                    emit_json({"success": False, "error": f"Entity '{eid}' in target does not exist"})
                else:
                    print(f"ERROR: Entity '{eid}' in target does not exist.")
                return

    condition = spec.get("condition", [])
    if isinstance(condition, dict):
        condition = [condition]

    automations = load_yaml(AGENT_YAML, default=[])

    if len(automations) >= MAX_AUTOMATIONS:
        if json_mode:
            emit_json({"success": False, "error": f"max {MAX_AUTOMATIONS} automations reached"})
        else:
            print(f"ERROR: Maximum {MAX_AUTOMATIONS} automations reached.")
        return

    for a in automations:
        if a.get("alias", "").lower() == alias.lower():
            if json_mode:
                emit_json({"success": False, "error": f"automation with alias '{alias}' already exists"})
            else:
                print(f"ERROR: Automation with alias '{alias}' already exists.")
            return

    new_auto = {
        "alias": alias,
        "id": auto_id,
        "trigger": trigger,
        "condition": condition,
        "action": action,
        "mode": "single"
    }
    automations.append(new_auto)

    if not save_automations(automations):
        automations.pop()
        save_automations(automations)
        if json_mode:
            emit_json({"success": False, "error": "invalid YAML after write. Automation not created."})
        else:
            print("ERROR: YAML validation failed. Automation not created.")
        return

    # v7.3-C — Pre-reload validation via Supervisor API
    config_ok, config_err = validate_ha_config(token)
    if not config_ok:
        # Automatic rollback
        automations.pop()
        save_automations(automations)
        if json_mode:
            emit_json({"success": False, "error": f"HA config invalid after add: {config_err}"})
        else:
            print(f"ERROR: HA config check failed: {config_err}. Automation rolled back.")
        return

    reloaded = reload_automations(token)
    if json_mode:
        emit_json({"success": True, "alias": alias, "id": auto_id, "reloaded": reloaded})
    else:
        if reloaded:
            print(f"Automation created: '{alias}' (id: {auto_id}). Active immediately.")
        else:
            print(f"Automation created: '{alias}' (id: {auto_id}). Reload failed, active on next HA restart.")


def cmd_create_from_file(token, json_mode=False):
    try:
        with open(PENDING_SPEC_PATH, 'r') as f:
            json_str = f.read().strip()
    except FileNotFoundError:
        if json_mode:
            emit_json({"success": False, "error": "pending spec file not found"})
        else:
            print("ERROR: No pending spec file found.")
        return
    cmd_create(json_str, token, json_mode=json_mode)


def cmd_remove(identifier, token, json_mode=False):
    automations = load_yaml(AGENT_YAML, default=[])
    identifier_lower = identifier.strip().lower()
    found_idx = None
    for i, a in enumerate(automations):
        if a.get("id", "").lower() == identifier_lower or \
           a.get("alias", "").lower() == identifier_lower:
            found_idx = i
            break
    if found_idx is None:
        if json_mode:
            emit_json({"success": False, "error": f"automation '{identifier}' not found"})
        else:
            print(f"ERROR: No automation found matching '{identifier}'.")
        return
    removed = automations.pop(found_idx)
    save_automations(automations)

    # v7.3-C — Pre-reload validation; if invalid, reinsert the removed automation
    config_ok, config_err = validate_ha_config(token)
    if not config_ok:
        automations.insert(found_idx, removed)
        save_automations(automations)
        if json_mode:
            emit_json({"success": False, "error": f"HA config invalid after remove: {config_err}"})
        else:
            print(f"ERROR: HA config check failed: {config_err}. Automation restored.")
        return

    reload_automations(token)
    if json_mode:
        emit_json({"success": True, "alias": removed.get("alias", "")})
    else:
        print(f"Automation removed: '{removed.get('alias')}'")


# ==============================================================================
# Commands - disable / enable
# ==============================================================================

def cmd_disable(identifier, json_mode=False):
    automations = load_yaml(AGENT_YAML, default=[])
    auto = _find_automation(automations, identifier)
    if not auto:
        if json_mode:
            emit_json({"success": False, "error": f"automation '{identifier}' not found"})
        else:
            print(f"Automation '{identifier}' not found.")
        return
    auto["initial_state"] = "off"
    save_yaml(AGENT_YAML, automations)
    if json_mode:
        emit_json({"success": True, "alias": auto.get("alias", ""), "enabled": False})
    else:
        print(f"Automation '{auto.get('alias', identifier)}' disabled.")


def cmd_enable(identifier, json_mode=False):
    automations = load_yaml(AGENT_YAML, default=[])
    auto = _find_automation(automations, identifier)
    if not auto:
        if json_mode:
            emit_json({"success": False, "error": f"automation '{identifier}' not found"})
        else:
            print(f"Automation '{identifier}' not found.")
        return
    auto["initial_state"] = "on"
    save_yaml(AGENT_YAML, automations)
    if json_mode:
        emit_json({"success": True, "alias": auto.get("alias", ""), "enabled": True})
    else:
        print(f"Automation '{auto.get('alias', identifier)}' re-enabled.")


# ==============================================================================
# Main dispatch
# ==============================================================================

def main():
    if len(sys.argv) < 2:
        print("Usage: manage_agent_automations.py <command> [args] [--json]")
        sys.exit(1)

    command = sys.argv[1].lower()
    args = sys.argv[2:]
    json_mode, args = parse_json_flag(args)
    token = load_token()

    if command == "list":
        cmd_list(json_mode=json_mode)
    elif command == "create":
        if not args:
            if json_mode:
                emit_json({"success": False, "error": "create requires JSON spec"})
            else:
                print("ERROR: JSON spec required.")
            sys.exit(1)
        cmd_create(" ".join(args), token, json_mode=json_mode)
    elif command == "create_from_file":
        cmd_create_from_file(token, json_mode=json_mode)
    elif command == "remove":
        if not args:
            if json_mode:
                emit_json({"success": False, "error": "remove requires alias or id"})
            else:
                print("ERROR: alias or id required.")
            sys.exit(1)
        cmd_remove(args[0], token, json_mode=json_mode)
    elif command == "details":
        if not args:
            if json_mode:
                emit_json({"success": False, "error": "details requires alias or id"})
            else:
                print("ERROR: alias or id required")
            sys.exit(1)
        cmd_details(args[0], json_mode=json_mode)
    elif command == "disable":
        if not args:
            if json_mode:
                emit_json({"success": False, "error": "disable requires alias or id"})
            else:
                print("ERROR: alias or id required")
            sys.exit(1)
        cmd_disable(args[0], json_mode=json_mode)
    elif command == "enable":
        if not args:
            if json_mode:
                emit_json({"success": False, "error": "enable requires alias or id"})
            else:
                print("ERROR: alias or id required")
            sys.exit(1)
        cmd_enable(args[0], json_mode=json_mode)
    elif command == "stats":
        cmd_stats(json_mode=json_mode)
    else:
        print(f"ERROR: Unknown command '{command}'.")
        sys.exit(1)


if __name__ == "__main__":
    main()
