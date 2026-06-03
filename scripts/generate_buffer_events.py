#!/usr/bin/env python3
"""
Generates the trigger block for permear_event_buffer from monitored_entities.json.
Reads the 'events' field of each entity and outputs YAML triggers.
Run manually after editing events in monitored_entities.json:
  python3 /config/scripts/generate_buffer_events.py
Then reload automations in HA.
"""
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import *

BEGIN_MARKER = "# [BEGIN buffer_eventos triggers — generated]"
END_MARKER   = "# [END buffer_eventos triggers — generated]"

# Markers for ARAS priority=2 entity triggers (in lockstep with events.yaml).
BEGIN_PRIO_MARKER = "    # [BEGIN aras_priority triggers — generated]"
END_PRIO_MARKER   = "    # [END aras_priority triggers — generated]"


def load_monitored():
    with open(ENTITIES_PATH, 'r') as f:
        return json.load(f)


def build_triggers_yaml(entities):
    lines = []
    for entity in entities:
        events = entity.get("events")
        if not events:
            continue
        entity_id = entity["entity_id"]
        for ev in events:
            trigger_type = ev.get("trigger_type", "state")
            ev_id = ev.get("id", "")
            if trigger_type == "state":
                lines.append(f"    - platform: state")
                lines.append(f"      entity_id: {entity_id}")
                if "to" in ev:
                    lines.append(f"      to: \"{ev['to']}\"")
                if "from" in ev:
                    lines.append(f"      from: \"{ev['from']}\"")
                if "for" in ev:
                    lines.append(f"      for: \"{ev['for']}\"")
                if ev_id:
                    lines.append(f"      id: \"{ev_id}\"")
            elif trigger_type == "numeric_state":
                lines.append(f"    - platform: numeric_state")
                lines.append(f"      entity_id: {entity_id}")
                if "above" in ev:
                    lines.append(f"      above: {ev['above']}")
                if "below" in ev:
                    lines.append(f"      below: {ev['below']}")
                if ev_id:
                    lines.append(f"      id: \"{ev_id}\"")
    return "\n".join(lines)


def update_events_yaml(new_triggers_yaml):
    with open(AUTOMATIONS_YAML, 'r') as f:
        content = f.read()

    if BEGIN_MARKER not in content:
        print(f"ERROR: Marker '{BEGIN_MARKER}' not found in {AUTOMATIONS_YAML}.")
        print("Add the markers manually around the trigger list in permear_event_buffer.")
        return False

    start = content.index(BEGIN_MARKER)
    end = content.index(END_MARKER) + len(END_MARKER)
    new_block = f"{BEGIN_MARKER}\n{new_triggers_yaml}\n{END_MARKER}"
    content = content[:start] + new_block + content[end:]

    with open(AUTOMATIONS_YAML, 'w') as f:
        f.write(content)
    return True


def build_priority_triggers_yaml(entities):
    """v7.5-C — Generates triggers for entities with priority >= 2."""
    lines = []
    for entity in entities:
        if not entity.get("monitor", True):  # v7.7-A: orphan priority — ignore monitor:false
            continue
        if int(entity.get("priority", 0)) < 2:
            continue
        eid = entity["entity_id"]
        lines.append(f"    - platform: state")
        lines.append(f"      entity_id: {eid}")
        lines.append(f"      id: \"aras_prio_{eid.replace('.', '_')}\"")
    return "\n".join(lines)


def update_priority_triggers(new_yaml):
    """Updates the [BEGIN/END aras_priority triggers] section in events.yaml."""
    with open(AUTOMATIONS_YAML, 'r') as f:
        content = f.read()
    if BEGIN_PRIO_MARKER not in content:
        print("INFO: aras_priority marker not found — priority=2 alert section not updated.")
        return False
    start = content.index(BEGIN_PRIO_MARKER)
    end = content.index(END_PRIO_MARKER) + len(END_PRIO_MARKER)
    new_block = f"{BEGIN_PRIO_MARKER}\n{new_yaml}\n{END_PRIO_MARKER}"
    content = content[:start] + new_block + content[end:]
    with open(AUTOMATIONS_YAML, 'w') as f:
        f.write(content)
    return True


def main():
    if not os.path.exists(ENTITIES_PATH):
        print(f"ERROR: {ENTITIES_PATH} not found.")
        sys.exit(1)

    data = load_monitored()
    entities = data.get("entities", [])

    triggers_yaml = build_triggers_yaml(entities)

    if not triggers_yaml.strip():
        print("WARNING: No events defined in monitored_entities.json. Nothing to generate.")
        sys.exit(0)

    trigger_count = triggers_yaml.count("- platform:")
    print(f"Generated {trigger_count} triggers.")

    if update_events_yaml(triggers_yaml):
        print(f"OK: {AUTOMATIONS_YAML} updated. Reload automations in HA to apply.")
    else:
        print("\n--- TRIGGERS YAML (paste manually) ---")
        print(triggers_yaml)

    # v7.5-C — also generate priority=2 entity triggers
    prio_yaml = build_priority_triggers_yaml(entities)
    prio_count = prio_yaml.count("- platform:") if prio_yaml.strip() else 0
    if update_priority_triggers(prio_yaml):
        print(f"OK: {prio_count} priority=2 trigger(s) updated.")


if __name__ == "__main__":
    main()
