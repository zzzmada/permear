#!/usr/bin/env python3
"""
Parse HA home-assistant.log and output compact health summary.
Designed for RPi4 performance: last 500 lines, 2h window.
"""
import re
import os
import sys
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import *

MAX_ERRORS = 5
MAX_WARNINGS = 5


def read_last_lines(path, max_lines=500, block_size=8192, max_bytes=10_000_000):
    """
    v7.3-B.1 — Reads the last N lines of a file using reverse-seek.
    RAM usage O(1) instead of O(N).

    Args:
        path: file path
        max_lines: maximum number of lines to return
        block_size: size of each read (bytes)
        max_bytes: safety limit — does not read more than 10MB
    Returns:
        list[str] with up to max_lines lines, already in chronological order
    """
    if not os.path.exists(path):
        return []

    file_size = os.path.getsize(path)
    if file_size == 0:
        return []

    read_limit = min(file_size, max_bytes)

    lines = []
    buffer = b""
    position = file_size

    try:
        with open(path, 'rb') as f:
            while position > 0 and len(lines) < max_lines and (file_size - position) < read_limit:
                read_size = min(block_size, position)
                position -= read_size
                f.seek(position)
                chunk = f.read(read_size)

                buffer = chunk + buffer

                parts = buffer.split(b'\n')
                if position > 0:
                    # First fragment may be incomplete — keep it for the next block
                    buffer = parts[0]
                    new_lines = parts[1:]
                else:
                    # Reached the start of the file — everything is valid
                    buffer = b""
                    new_lines = parts

                lines = new_lines + lines

        # Filter empties (trailing \n produces b"") before truncating to max_lines
        non_empty = [l for l in lines if l]
        decoded = []
        for line in non_empty[-max_lines:]:
            try:
                decoded.append(line.decode('utf-8', errors='replace'))
            except Exception:
                continue
        return decoded

    except (IOError, OSError) as e:
        print(f"WARNING: read_last_lines failed: {e}", file=sys.stderr)
        return []


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

    # v7.3-B.1 — Reverse-seek instead of readlines() (RAM O(1) vs O(N))
    lines = read_last_lines(HA_LOG_PATH, max_lines=500)
    if not lines:
        print("HEALTH: OK")
        return

    for line in lines:
        # Try to extract timestamp
        ts_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
        if ts_match:
            try:
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
                # Unstructured error line: check if any SELF_COMPONENT keyword appears
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
            new_devices.append(line.strip()[:80])

    # Build compact output
    parts = []
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


if __name__ == "__main__":
    parse_log()
