#!/usr/bin/env python3
<<<<<<< HEAD
"""Generate automation trigger YAML from monitored_entities.json events."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import ENTITIES_PATH, AUTOMATIONS_YAML
BEGIN_MARKER = "# [BEGIN buffer_events triggers — generated]"
END_MARKER = "# [END buffer_events triggers — generated]"
def build_triggers(entities):
    lines = []
    for ent in entities:
        events = ent.get("events")
        if not events: continue
        eid = ent["entity_id"]
        for ev in events:
            tt = ev.get("trigger_type", "state")
            if tt == "state":
                lines.append(f"    - platform: state")
                lines.append(f"      entity_id: {eid}")
                for k in ["to", "from"]:
                    if k in ev: lines.append(f'      {k}: "{ev[k]}"')
                if "for" in ev: lines.append(f'      for: "{ev["for"]}"')
                if ev.get("id"): lines.append(f'      id: "{ev["id"]}"')
            elif tt == "numeric_state":
                lines.append(f"    - platform: numeric_state")
                lines.append(f"      entity_id: {eid}")
                for k in ["above", "below"]:
                    if k in ev: lines.append(f"      {k}: {ev[k]}")
                if ev.get("id"): lines.append(f'      id: "{ev["id"]}"')
    return "\n".join(lines)
def main():
    if not os.path.exists(ENTITIES_PATH):
        print(f"ERROR: {ENTITIES_PATH} not found."); sys.exit(1)
    with open(ENTITIES_PATH, 'r') as f: data = json.load(f)
    triggers = build_triggers(data.get("entities", []))
    if not triggers.strip(): print("WARNING: No events defined."); sys.exit(0)
    print(f"Generated {triggers.count('- platform:')} triggers.")
    with open(AUTOMATIONS_YAML, 'r') as f: content = f.read()
    if BEGIN_MARKER not in content:
        print(f"ERROR: Marker not found in {AUTOMATIONS_YAML}.")
        print("\n--- PASTE MANUALLY ---\n" + triggers); return
    start = content.index(BEGIN_MARKER)
    end = content.index(END_MARKER) + len(END_MARKER)
    content = content[:start] + f"{BEGIN_MARKER}\n{triggers}\n    {END_MARKER}" + content[end:]
    with open(AUTOMATIONS_YAML, 'w') as f: f.write(content)
    print(f"OK: {AUTOMATIONS_YAML} updated. Reload automations.")
=======
"""
Generates the trigger block for permear_buffer_events from monitored_entities.json.
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

BEGIN_MARKER = "# [BEGIN buffer_events triggers - generated]"
END_MARKER   = "# [END buffer_events triggers - generated]"


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


def update_yaml(new_triggers_yaml):
    with open(AUTOMATIONS_YAML, 'r') as f:
        content = f.read()

    if BEGIN_MARKER not in content:
        print(f"ERROR: Marker '{BEGIN_MARKER}' not found in {AUTOMATIONS_YAML}.")
        print("Add the markers manually around the trigger list in permear_buffer_events.")
        return False

    start = content.index(BEGIN_MARKER)
    end = content.index(END_MARKER) + len(END_MARKER)
    new_block = f"{BEGIN_MARKER}\n{new_triggers_yaml}\n{END_MARKER}"
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

    if update_yaml(triggers_yaml):
        print(f"OK: {AUTOMATIONS_YAML} updated. Reload automations in HA to apply.")
    else:
        print("\n--- TRIGGERS YAML (paste manually) ---")
        print(triggers_yaml)


>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
if __name__ == "__main__":
    main()
