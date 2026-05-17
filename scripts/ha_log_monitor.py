#!/usr/bin/env python3
<<<<<<< HEAD
"""Parse HA log. SELF_ERRORS (agent's own) vs ERRORS (external)."""
import re, os, sys
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import HA_LOG_PATH, SELF_COMPONENTS
MAX_ERRORS, MAX_WARNINGS, LOOKBACK_HOURS = 10, 5, 2
def is_self(comp):
    return any(sc in comp.lower() for sc in SELF_COMPONENTS)
def main():
    if not os.path.exists(HA_LOG_PATH): print("HEALTH: Log not found"); return
    cutoff = datetime.now() - timedelta(hours=LOOKBACK_HOURS)
    self_errors, other_errors, warnings, new_devices = [], [], [], []
    unavailable, seen = set(), set()
    try:
        with open(HA_LOG_PATH, 'r', errors='replace') as f: lines = f.readlines()
    except Exception as e: print(f"HEALTH: Read error — {e}"); return
=======
"""
Parse HA home-assistant.log and output compact health summary.
Designed for RPi4 performance: last 500 lines, 2h window.
v7.0: uses lib helpers.
"""
import re
import os
import sys
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import *

MAX_ERRORS = 5
MAX_WARNINGS = 5


def is_self_component(component_str):
    """Check if the error component matches a PERMEAR-related component."""
    comp_lower = component_str.lower()
    return any(sc in comp_lower for sc in SELF_COMPONENTS)


def parse_log():
    cutoff = datetime.now() - timedelta(hours=2)
    seen = set()
    self_errors = []
    other_errors = []
    warnings = []
    unavailable = []
    new_devices = []

    try:
        with open(HA_LOG_PATH, 'r', errors='replace') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print("HEALTH: OK")
        return

    # Process last 500 lines max (performance on RPi4)
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
    for line in lines[-500:]:
        # Try to extract timestamp
        ts_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
        if ts_match:
            try:
<<<<<<< HEAD
                if datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S") < cutoff: continue
            except: continue
        dk = line[:80]
        if dk in seen: continue
        seen.add(dk)
        if " ERROR " in line:
            match = re.search(r'ERROR \((\w+)\) \[([^\]]+)\] (.+)', line)
            if match:
                comp = match.group(2); msg = match.group(3)[:80]
                t = ts_match.group(1)[11:16] if ts_match else "?"
                entry = f"{comp.split('.')[-1]} {t}: {msg}"
                if is_self(comp):
                    if len(self_errors) < MAX_ERRORS: self_errors.append(entry)
                else:
                    if len(other_errors) < MAX_ERRORS: other_errors.append(entry)
            else:
                t = ts_match.group(1)[11:16] if ts_match else "?"
                entry = f"{t}: {line.strip()[:80]}"
                if any(sc in line.lower() for sc in SELF_COMPONENTS):
                    if len(self_errors) < MAX_ERRORS: self_errors.append(entry)
                elif len(other_errors) < MAX_ERRORS: other_errors.append(entry)
        elif " WARNING " in line:
            if "unavailable" in line.lower():
                m = re.search(r'([\w]+\.[\w]+)', line)
                if m: unavailable.add(m.group(1))
            elif len(warnings) < MAX_WARNINGS:
                m = re.search(r'WARNING \((\w+)\) \[([^\]]+)\] (.+)', line)
                if m: warnings.append(f"{m.group(2).split('.')[-1]}: {m.group(3)[:60]}")
        ll = line.lower()
        if ("interview" in ll or "new device" in ll) and ("zigbee" in ll or "z2m" in ll):
=======
                ts = datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S")
                if ts < cutoff:
                    continue
            except ValueError:
                continue

        # Dedup key: first 80 chars
        dedup_key = line[:80]
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        # Classify
        if " ERROR " in line:
            match = re.search(r'ERROR \((\w+)\) \[([^\]]+)\] (.+)', line)
            if match:
                component = match.group(2)
                component_short = component.split('.')[-1]
                msg = match.group(3)[:60]
                time_str = ts_match.group(1)[11:16] if ts_match else "?"
                entry = f"{component_short} {time_str}: {msg}"
                if is_self_component(component):
                    self_errors.append(entry)
                else:
                    other_errors.append(entry)
            else:
                entry = line.strip()[:80]
                if is_self_component(line):
                    if len(self_errors) < MAX_ERRORS:
                        self_errors.append(entry)
                else:
                    if len(other_errors) < MAX_ERRORS:
                        other_errors.append(entry)

        elif " WARNING " in line:
            if "unavailable" in line.lower():
                ent_match = re.search(r'([\w]+\.[\w]+)', line)
                if ent_match:
                    ent = ent_match.group(1)
                    if ent not in [u.split()[0] for u in unavailable]:
                        unavailable.append(ent)
            elif len(warnings) < MAX_WARNINGS:
                match = re.search(r'WARNING \((\w+)\) \[([^\]]+)\] (.+)', line)
                if match:
                    component = match.group(2).split('.')[-1]
                    msg = match.group(3)[:60]
                    warnings.append(f"{component}: {msg}")

        # Zigbee2MQTT new device
        if "zigbee2mqtt" in line.lower() and ("interview" in line.lower() or "new device" in line.lower()):
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
            new_devices.append(line.strip()[:80])
    parts = []
<<<<<<< HEAD
    if self_errors: parts.append(f"SELF_ERRORS({len(self_errors)}): " + " | ".join(self_errors))
    if other_errors: parts.append(f"ERRORS({len(other_errors)}): " + " | ".join(other_errors))
    if warnings: parts.append(f"WARNINGS({len(warnings)}): " + " | ".join(warnings))
    if unavailable: parts.append(f"UNAVAILABLE: " + ", ".join(sorted(unavailable)[:10]))
    if new_devices: parts.append(f"NEW_DEVICES: " + " | ".join(new_devices[:3]))
    print("\n".join(parts) if parts else "HEALTH: OK")
=======
    if self_errors:
        parts.append(f"SELF_ERRORS({len(self_errors)}): " + " | ".join(self_errors[:MAX_ERRORS]))
    if other_errors:
        parts.append(f"ERRORS({len(other_errors)}): " + " | ".join(other_errors[:MAX_ERRORS]))
    if warnings:
        parts.append(f"WARNINGS({len(warnings)}): " + " | ".join(warnings[:MAX_WARNINGS]))
    if unavailable:
        parts.append(f"UNAVAILABLE: " + ", ".join(unavailable[:10]))
    if new_devices:
        parts.append(f"NEW_DEVICES: " + " | ".join(new_devices[:3]))

    if parts:
        print("\n".join(parts))
    else:
        print("HEALTH: OK")


>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
if __name__ == "__main__":
    parse_log()
