#!/usr/bin/env python3
"""
HA Updates manager via REST API and Supervisor API.
Usage:
  ha_update_manager.py list
  ha_update_manager.py list_pending_json
  ha_update_manager.py check_backup
  ha_update_manager.py execute <entity_id>
  ha_update_manager.py skip <entity_id>
  ha_update_manager.py create_backup
"""
import json
import os
import sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import URLError
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import TOKEN_PATH, HA_URL

SUPERVISOR_URL = "http://supervisor"


def load_token():
    try:
        with open(TOKEN_PATH, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def ha_api(endpoint, method="GET", data=None, token=None):
    url = f"{HA_URL}/api/{endpoint}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = json.dumps(data).encode() if data else None
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except URLError:
        return None


def supervisor_api(endpoint, method="GET", data=None):
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not token:
        token = load_token()
    url = f"{SUPERVISOR_URL}/{endpoint}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = json.dumps(data).encode() if data else None
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except URLError:
        return None


def _classify_entity(entity_id):
    """Return category: addon, core, or haos."""
    eid_lower = entity_id.lower()
    if "homeassistant" in eid_lower and "os" in eid_lower:
        return "haos"
    if entity_id == "update.home_assistant_core_update" or "core" in eid_lower:
        return "core"
    return "addon"


def cmd_list():
    token = load_token()
    result = ha_api("states", token=token)
    if result is None:
        print("Could not query HA.")
        return

    addons = []
    core = []
    haos = []

    for state in result:
        entity_id = state.get("entity_id", "")
        if not entity_id.startswith("update."):
            continue
        attrs = state.get("attributes", {})
        if state.get("state") != "on":
            continue
        if attrs.get("skipped_version"):
            continue

        name = attrs.get("friendly_name", entity_id)
        cur = attrs.get("installed_version", "?")
        new = attrs.get("latest_version", "?")
        entry = (name, cur, new, entity_id)

        category = _classify_entity(entity_id)
        if category == "haos":
            haos.append(entry)
        elif category == "core":
            core.append(entry)
        else:
            addons.append(entry)

    all_updates = addons + core + haos
    if not all_updates:
        print("No updates available.")
        return

    lines = [f"Updates available ({len(all_updates)}):"]
    for i, (name, cur, new, _) in enumerate(all_updates, 1):
        lines.append(f"{i}. {name} {cur} to {new}")
    print("\n".join(lines))


def cmd_check_backup():
    result = supervisor_api("backups")
    if result is None or result.get("result") != "ok":
        print("Could not query backups.")
        return

    backups = result.get("data", {}).get("backups", [])
    if not backups:
        print("No backups found.")
        return

    most_recent = None
    most_recent_dt = None
    for b in backups:
        date_str = b.get("date", "")
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            if most_recent_dt is None or dt > most_recent_dt:
                most_recent_dt = dt
                most_recent = b
        except (ValueError, AttributeError):
            continue

    if most_recent is None:
        print("Could not determine most recent backup.")
        return

    name = most_recent.get("name", "backup")
    now = datetime.now(timezone.utc)
    age_seconds = (now - most_recent_dt).total_seconds()
    age_hours = int(age_seconds / 3600)
    age_days = int(age_hours / 24)

    if age_days >= 1:
        age_txt = f"{age_days} day{'s' if age_days > 1 else ''}"
        print(f"Old backup: {name} is {age_txt} old. Recommend creating a new one before updating.")
    else:
        print(f"Backup OK: {name} is {age_hours} hour{'s' if age_hours != 1 else ''} old.")


def cmd_execute(entity_id):
    token = load_token()
    domain, _, _ = entity_id.partition(".")
    if domain != "update":
        print(f"Invalid entity: {entity_id}. Must be from 'update' domain.")
        return

    result = ha_api("services/update/install", method="POST",
                    data={"entity_id": entity_id}, token=token)
    if result is not None:
        attrs = ha_api(f"states/{entity_id}", token=token)
        name = attrs.get("attributes", {}).get("friendly_name", entity_id) if attrs else entity_id
        print(f"Update started: {name}.")
    else:
        print(f"Error starting update for {entity_id}.")


def cmd_skip(entity_id):
    token = load_token()
    result = ha_api("services/update/skip", method="POST",
                    data={"entity_id": entity_id}, token=token)
    if result is not None:
        attrs = ha_api(f"states/{entity_id}", token=token)
        name = attrs.get("attributes", {}).get("friendly_name", entity_id) if attrs else entity_id
        print(f"Update skipped: {name}. Will be notified again on next version.")
    else:
        print(f"Error skipping update for {entity_id}.")


def cmd_list_pending_json():
    token = load_token()
    result = ha_api("states", token=token)
    if result is None:
        print("[]")
        return

    addons = []
    core = []
    haos = []

    for state in result:
        entity_id = state.get("entity_id", "")
        if not entity_id.startswith("update."):
            continue
        if state.get("state") != "on":
            continue
        attrs = state.get("attributes", {})
        if attrs.get("skipped_version"):
            continue

        name = attrs.get("friendly_name", entity_id)
        cur = attrs.get("installed_version", "?")
        new = attrs.get("latest_version", "?")
        entry = {"entity_id": entity_id, "name": name, "current": cur, "latest": new}

        category = _classify_entity(entity_id)
        if category == "haos":
            haos.append(entry)
        elif category == "core":
            core.append(entry)
        else:
            addons.append(entry)

    print(json.dumps(addons + core + haos, ensure_ascii=False))


def cmd_create_backup():
    now = datetime.now()
    backup_name = f"permear_pre_update_{now.strftime('%Y%m%d_%H%M')}"
    result = supervisor_api("backups/new/full", method="POST",
                            data={"name": backup_name})
    if result and result.get("result") == "ok":
        print("Backup created successfully.")
    else:
        print("Error creating backup.")


def main():
    if len(sys.argv) < 2:
        print("Usage: ha_update_manager.py [list|list_pending_json|check_backup|execute|skip|create_backup]")
        return

    command = sys.argv[1].lower()

    if command == "list":
        cmd_list()
    elif command == "list_pending_json":
        cmd_list_pending_json()
    elif command == "check_backup":
        cmd_check_backup()
    elif command == "execute":
        if len(sys.argv) < 3:
            print("Provide the update entity_id.")
            return
        cmd_execute(sys.argv[2])
    elif command == "skip":
        if len(sys.argv) < 3:
            print("Provide the update entity_id.")
            return
        cmd_skip(sys.argv[2])
    elif command == "create_backup":
        cmd_create_backup()
    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
