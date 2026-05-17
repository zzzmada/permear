#!/usr/bin/env python3
"""
Check HA Core and addon updates via Supervisor API.
The Supervisor API is available at http://supervisor/ inside HAOS containers
with the SUPERVISOR_TOKEN environment variable.
"""
import json
import os
import sys
from urllib.request import Request, urlopen
from urllib.error import URLError
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import *

SUPERVISOR_URL = "http://supervisor"


def supervisor_api(endpoint):
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not token:
        try:
            with open(TOKEN_PATH, 'r') as f:
                token = f.read().strip()
        except FileNotFoundError:
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

    # Core info
    core = supervisor_api("core/info")
    if core and core.get("result") == "ok":
        data = core.get("data", {})
        current = data.get("version", "?")
        latest = data.get("version_latest", "?")
        if current != latest:
            parts.append(f"HA_CORE: {current} -> {latest} available")

    # Addon updates
    addons = supervisor_api("addons")
    if addons and addons.get("result") == "ok":
        addon_updates = []
        for addon in addons.get("data", {}).get("addons", []):
            if addon.get("update_available", False):
                name = addon.get("name", "?")
                cur = addon.get("version", "?")
                new = addon.get("version_latest", "?")
                addon_updates.append(f"{name} {cur}->{new}")
        if addon_updates:
            parts.append(f"ADDONS_UPDATE({len(addon_updates)}): " + ", ".join(addon_updates[:5]))

    # Disk usage
    host = supervisor_api("host/info")
    if host and host.get("result") == "ok":
        data = host.get("data", {})
        disk_total = data.get("disk_total", 0)
        disk_used = data.get("disk_used", 0)
        disk_free = data.get("disk_free", 0)
        if disk_total and disk_total > 0:
            pct = int(disk_used * 100 / disk_total)
            free_gb = round(disk_free / 1024, 1) if disk_free > 1024 else disk_free
            unit = "GB" if disk_free > 1024 else "MB"
            if pct >= 80:
                parts.append(f"DISK: {pct}% used ({free_gb}{unit} free) - ATTENTION")
            else:
                parts.append(f"DISK: {pct}% used ({free_gb}{unit} free)")

    if parts:
        print("\n".join(parts))
    else:
        print("UPDATES: none")


if __name__ == "__main__":
    main()
