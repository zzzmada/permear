#!/usr/bin/env python3
"""Check HA/addon updates via Supervisor API. Only works inside HAOS container."""
import json, os
from urllib.request import Request, urlopen
from urllib.error import URLError
def supervisor_api(endpoint):
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not token: return None
    try:
        with urlopen(Request(f"http://supervisor/{endpoint}",
                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}), timeout=10) as r:
            return json.loads(r.read().decode())
    except URLError: return None
def main():
    parts = []
    core = supervisor_api("core/info")
    if core and core.get("result") == "ok":
        d = core["data"]; cur, lat = d.get("version","?"), d.get("version_latest","?")
        parts.append(f"HA_CORE: {cur} -> {lat} available" if cur != lat else f"HA_CORE: {cur} (up to date)")
    os_info = supervisor_api("os/info")
    if os_info and os_info.get("result") == "ok":
        d = os_info["data"]; cur, lat = d.get("version","?"), d.get("version_latest","?")
        if cur != lat: parts.append(f"HAOS: {cur} -> {lat} available")
    addons = supervisor_api("addons")
    if addons and addons.get("result") == "ok":
        u = [f"{a.get('name','?')} {a.get('version','?')}->{a.get('version_latest','?')}"
             for a in addons.get("data",{}).get("addons",[]) if a.get("update_available")]
        if u: parts.append(f"ADDON_UPDATES({len(u)}): " + ", ".join(u))
    print("\n".join(parts) if parts else "UPDATES: Could not reach Supervisor API")
if __name__ == "__main__":
    main()
