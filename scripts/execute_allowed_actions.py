#!/usr/bin/env python3
"""
PERMEAR v4.0 — Execute allowed autonomous actions.
Reads allowed_actions.json, evaluates conditions against HA state,
executes matching actions via HA REST API, returns results.

Requires: Long-lived access token in /config/.permear_token
Create one in HA: Profile → Long-Lived Access Tokens → Create Token
Then: echo "YOUR_TOKEN" > /config/.permear_token && chmod 600 /config/.permear_token
"""
import json, os, sys
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from urllib.error import URLError

ACTIONS_PATH = "/config/memory/allowed_actions.json"
TOKEN_PATH = "/config/.permear_token"
HA_URL = "http://localhost:8123"

def load_token():
    try:
        with open(TOKEN_PATH, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        print("ERROR: Token file not found at /config/.permear_token")
        print("Create one: Profile → Long-Lived Access Tokens → Create Token")
        print("Then: echo 'YOUR_TOKEN' > /config/.permear_token")
        return None

def ha_api(endpoint, method="GET", data=None, token=None):
    """Call HA REST API."""
    url = f"{HA_URL}/api/{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    body = json.dumps(data).encode() if data else None
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except URLError as e:
        print(f"HA API error: {e}")
        return None

def get_entity_state(entity_id, token):
    """Get current state of an HA entity."""
    result = ha_api(f"states/{entity_id}", token=token)
    if result:
        return result.get("state")
    return None

def execute_service(service, data, token):
    """Call an HA service."""
    domain, action = service.split(".", 1)
    result = ha_api(f"services/{domain}/{action}", method="POST", data=data, token=token)
    return result is not None

def evaluate_condition(condition, token):
    """Evaluate a single condition. Returns (bool, trigger_value)."""
    cond_type = condition.get("type", "entity")

    if cond_type == "time_after":
        now = datetime.now().strftime("%H:%M")
        return now >= condition["value"], now

    if cond_type == "time_before":
        now = datetime.now().strftime("%H:%M")
        return now <= condition["value"], now

    # Entity-based condition
    entity = condition.get("entity")
    if not entity:
        return False, None

    state_raw = get_entity_state(entity, token)
    if state_raw is None or state_raw in ["unavailable", "unknown"]:
        return False, None

    operator = condition.get("operator", "==")
    expected = condition.get("value")

    # Try numeric comparison
    try:
        state_val = float(state_raw)
        expected_val = float(expected)
        ops = {
            ">=": state_val >= expected_val,
            "<=": state_val <= expected_val,
            ">": state_val > expected_val,
            "<": state_val < expected_val,
            "==": state_val == expected_val,
            "!=": state_val != expected_val,
        }
        return ops.get(operator, False), state_raw
    except (ValueError, TypeError):
        # String comparison
        if operator == "==":
            return str(state_raw) == str(expected), state_raw
        elif operator == "!=":
            return str(state_raw) != str(expected), state_raw
        return False, state_raw

def check_cooldown(action):
    """Check if cooldown period has passed since last execution."""
    cooldown = action.get("cooldown_minutes", 60)
    last = action.get("last_executed")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
        return datetime.now() - last_dt > timedelta(minutes=cooldown)
    except (ValueError, TypeError):
        return True

def main():
    token = load_token()
    if not token:
        return

    # Load actions
    try:
        with open(ACTIONS_PATH, 'r') as f:
            actions_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"ERROR: Cannot read {ACTIONS_PATH}: {e}")
        return

    approved = actions_data.get("approved", [])
    if not approved:
        print("NO_ACTIONS")
        return

    executed = []

    for action in approved:
        action_id = action.get("id", "unknown")

        # Check cooldown
        if not check_cooldown(action):
            continue

        # Evaluate ALL conditions (AND logic)
        all_met = True
        trigger_value = None
        for condition in action.get("conditions", []):
            met, val = evaluate_condition(condition, token)
            if not met:
                all_met = False
                break
            if val and condition.get("type", "entity") == "entity":
                trigger_value = val  # Keep the entity value that triggered

        if not all_met:
            continue

        # Execute action
        service = action["action"].get("service")
        data = action["action"].get("data", {})
        if not service:
            continue

        success = execute_service(service, data, token)
        if success:
            # Format notification
            notification = action.get("notification", f"Executed action: {action_id}")
            if trigger_value:
                notification = notification.replace("{trigger_value}", str(trigger_value))

            # Update last_executed
            action["last_executed"] = datetime.now().isoformat()

            executed.append({
                "id": action_id,
                "notification": notification,
                "description": action.get("description", "")
            })

    # Save updated timestamps
    if executed:
        with open(ACTIONS_PATH, 'w') as f:
            json.dump(actions_data, f, ensure_ascii=False, indent=2)

    # Output results
    if executed:
        print(json.dumps({"executed": executed}, ensure_ascii=False))
    else:
        print("NO_ACTIONS")

if __name__ == "__main__":
    main()
