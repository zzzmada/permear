#!/usr/bin/env python3
"""
Check HA Core and addon updates via Supervisor API.

IMPORTANT: This script only works inside the HAOS container where
SUPERVISOR_TOKEN exists as an environment variable. It cannot be
tested from SSH addons or external terminals. Run it via HA's
shell_command service (Developer Tools → Services).
"""
import json, os
from urllib.request import Request, urlopen
from urllib.error import URLError

SUPERVISOR_URL = "http://supervisor"

def supervisor_api(endpoint):
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not token:
        return None

    url = f"{SUPERVISOR_URL}/{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except URLError:
        return None

def main():
    parts = []

    core = supervisor_api("core/info")
    if core and core.get("result") == "ok":
        data = core.get("data", {})
        current = data.get("version", "?")
        latest = data.get("version_latest", "?")
        if current != latest:
            parts.append(f"HA_CORE: {current} -> {latest} available")
        else:
            parts.append(f"HA_CORE: {current} (up to date)")

    os_info = supervisor_api("os/info")
    if os_info and os_info.get("result") == "ok":
        data = os_info.get("data", {})
        current = data.get("version", "?")
        latest = data.get("version_latest", "?")
        if current != latest:
            parts.append(f"HAOS: {current} -> {latest} available")

    addons = supervisor_api("addons")
    if addons and addons.get("result") == "ok":
        updates = []
        for addon in addons.get("data", {}).get("addons", []):
            if addon.get("update_available", False):
                name = addon.get("name", "?")
                cur = addon.get("version", "?")
                new = addon.get("version_latest", "?")
                updates.append(f"{name} {cur}->{new}")
        if updates:
            parts.append(f"ADDON_UPDATES({len(updates)}): " + ", ".join(updates))

    if not parts:
        # SUPERVISOR_TOKEN might not be available
        print("UPDATES: Could not reach Supervisor API (normal if running outside HAOS container)")
    else:
        print("\n".join(parts))

if __name__ == "__main__":
    main()
