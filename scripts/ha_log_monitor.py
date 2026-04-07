#!/usr/bin/env python3
"""
Parse HA log file and return compact summary of errors, warnings,
and unavailable entities. Output optimized for token economy.
"""
import re, os
from datetime import datetime, timedelta
from collections import defaultdict

LOG_PATH = "/config/home-assistant.log"
MAX_ERRORS = 10
MAX_WARNINGS = 5
LOOKBACK_HOURS = 2

def main():
    if not os.path.exists(LOG_PATH):
        print("HEALTH: Log file not found")
        return

    cutoff = datetime.now() - timedelta(hours=LOOKBACK_HOURS)
    errors = []
    warnings = []
    unavailable = set()
    new_devices = []
    seen = set()

    try:
        with open(LOG_PATH, 'r', errors='replace') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"HEALTH: Read error — {e}")
        return

    # Process last 500 lines max (performance on low-RAM devices)
    for line in lines[-500:]:
        ts_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
        if ts_match:
            try:
                ts = datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S")
                if ts < cutoff:
                    continue
            except ValueError:
                continue

        # Dedup by first 80 chars
        dedup_key = line[:80]
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        if " ERROR " in line:
            match = re.search(r'ERROR \((\w+)\) \[([^\]]+)\] (.+)', line)
            if match and len(errors) < MAX_ERRORS:
                component = match.group(2).split('.')[-1]
                msg = match.group(3)[:60]
                time_str = ts_match.group(1)[11:16] if ts_match else "?"
                errors.append(f"{component} {time_str}: {msg}")

        elif " WARNING " in line:
            if "unavailable" in line.lower():
                ent_match = re.search(r'([\w]+\.[\w]+)', line)
                if ent_match:
                    unavailable.add(ent_match.group(1))
            elif len(warnings) < MAX_WARNINGS:
                match = re.search(r'WARNING \((\w+)\) \[([^\]]+)\] (.+)', line)
                if match:
                    component = match.group(2).split('.')[-1]
                    msg = match.group(3)[:60]
                    warnings.append(f"{component}: {msg}")

        # New Zigbee/Z-Wave devices
        line_lower = line.lower()
        if ("interview" in line_lower or "new device" in line_lower) and \
           ("zigbee" in line_lower or "zwave" in line_lower or "z2m" in line_lower):
            new_devices.append(line.strip()[:80])

    # Build compact output
    parts = []
    if errors:
        parts.append(f"ERRORS({len(errors)}): " + " | ".join(errors))
    if warnings:
        parts.append(f"WARNINGS({len(warnings)}): " + " | ".join(warnings))
    if unavailable:
        parts.append(f"UNAVAILABLE: " + ", ".join(sorted(unavailable)[:10]))
    if new_devices:
        parts.append(f"NEW_DEVICES: " + " | ".join(new_devices[:3]))

    print("\n".join(parts) if parts else "HEALTH: OK")

if __name__ == "__main__":
    main()
