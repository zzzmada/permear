#!/usr/bin/env python3
"""
Parse HA log file. Returns compact summary with two error categories:
- SELF_ERRORS: errors from components PERMEAR uses directly (telegram, conversation,
  automation, shell_command). These are likely caused by the agent's own actions.
- ERRORS: errors from other HA components (external integrations, devices, etc.)
"""
import re, os
from datetime import datetime, timedelta

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import HA_LOG_PATH, SELF_COMPONENTS

MAX_ERRORS = 10
MAX_WARNINGS = 5
LOOKBACK_HOURS = 2

def is_self_component(component_str):
    """Check if the error component matches a PERMEAR-related component."""
    comp_lower = component_str.lower()
    return any(sc in comp_lower for sc in SELF_COMPONENTS)

def main():
    if not os.path.exists(HA_LOG_PATH):
        print("HEALTH: Log file not found")
        return

    cutoff = datetime.now() - timedelta(hours=LOOKBACK_HOURS)
    self_errors = []
    other_errors = []
    warnings = []
    new_devices = []
    unavailable = set()
    seen = set()

    try:
        with open(HA_LOG_PATH, 'r', errors='replace') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"HEALTH: Read error — {e}")
        return

    for line in lines[-500:]:
        ts_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
        if ts_match:
            try:
                if datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S") < cutoff:
                    continue
            except ValueError:
                continue

        dedup_key = line[:80]
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        if " ERROR " in line:
            # Try structured format: ERROR (thread) [component] message
            match = re.search(r'ERROR \((\w+)\) \[([^\]]+)\] (.+)', line)
            if match:
                component = match.group(2)
                component_short = component.split('.')[-1]
                msg = match.group(3)[:80]
                time_str = ts_match.group(1)[11:16] if ts_match else "?"
                entry = f"{component_short} {time_str}: {msg}"

                if is_self_component(component):
                    if len(self_errors) < MAX_ERRORS:
                        self_errors.append(entry)
                else:
                    if len(other_errors) < MAX_ERRORS:
                        other_errors.append(entry)
            else:
                # Unstructured error — check if it mentions a self component
                line_lower = line.lower()
                if any(sc in line_lower for sc in SELF_COMPONENTS):
                    if len(self_errors) < MAX_ERRORS:
                        time_str = ts_match.group(1)[11:16] if ts_match else "?"
                        self_errors.append(f"{time_str}: {line.strip()[:80]}")
                elif len(other_errors) < MAX_ERRORS:
                    time_str = ts_match.group(1)[11:16] if ts_match else "?"
                    other_errors.append(f"{time_str}: {line.strip()[:80]}")

        elif " WARNING " in line:
            if "unavailable" in line.lower():
                ent_match = re.search(r'([\w]+\.[\w]+)', line)
                if ent_match:
                    unavailable.add(ent_match.group(1))
            elif len(warnings) < MAX_WARNINGS:
                match = re.search(r'WARNING \((\w+)\) \[([^\]]+)\] (.+)', line)
                if match:
                    warnings.append(f"{match.group(2).split('.')[-1]}: {match.group(3)[:60]}")

        # New Zigbee/Z-Wave devices
        ll = line.lower()
        if ("interview" in ll or "new device" in ll) and ("zigbee" in ll or "z2m" in ll):
            new_devices.append(line.strip()[:80])

    # Build compact output
    parts = []
    if self_errors:
        parts.append(f"SELF_ERRORS({len(self_errors)}): " + " | ".join(self_errors))
    if other_errors:
        parts.append(f"ERRORS({len(other_errors)}): " + " | ".join(other_errors))
    if warnings:
        parts.append(f"WARNINGS({len(warnings)}): " + " | ".join(warnings))
    if unavailable:
        parts.append(f"UNAVAILABLE: " + ", ".join(sorted(unavailable)[:10]))
    if new_devices:
        parts.append(f"NEW_DEVICES: " + " | ".join(new_devices[:3]))

    print("\n".join(parts) if parts else "HEALTH: OK")

if __name__ == "__main__":
    main()
