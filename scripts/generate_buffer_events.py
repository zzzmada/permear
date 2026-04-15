#!/usr/bin/env python3
"""Generate automation trigger YAML from monitored_entities.json events field."""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import ENTITIES_PATH, AUTOMATIONS_YAML

BEGIN_MARKER = "# [BEGIN buffer_events triggers — generated]"
END_MARKER = "# [END buffer_events triggers — generated]"

def build_triggers_yaml(entities):
    lines = []
    for entity in entities:
        events = entity.get("events")
        if not events:
            continue
        eid = entity["entity_id"]
        for ev in events:
            tt = ev.get("trigger_type", "state")
            ev_id = ev.get("id", "")
            if tt == "state":
                lines.append(f"    - platform: state")
                lines.append(f"      entity_id: {eid}")
                for k in ["to", "from"]:
                    if k in ev:
                        lines.append(f'      {k}: "{ev[k]}"')
                if "for" in ev:
                    lines.append(f'      for: "{ev["for"]}"')
                if ev_id:
                    lines.append(f'      id: "{ev_id}"')
            elif tt == "numeric_state":
                lines.append(f"    - platform: numeric_state")
                lines.append(f"      entity_id: {eid}")
                for k in ["above", "below"]:
                    if k in ev:
                        lines.append(f"      {k}: {ev[k]}")
                if ev_id:
                    lines.append(f'      id: "{ev_id}"')
    return "\n".join(lines)

def main():
    if not os.path.exists(ENTITIES_PATH):
        print(f"ERROR: {ENTITIES_PATH} not found.")
        sys.exit(1)
    with open(ENTITIES_PATH, 'r') as f:
        data = json.load(f)
    triggers = build_triggers_yaml(data.get("entities", []))
    if not triggers.strip():
        print("WARNING: No events defined.")
        sys.exit(0)
    print(f"Generated {triggers.count('- platform:')} triggers.")
    with open(AUTOMATIONS_YAML, 'r') as f:
        content = f.read()
    if BEGIN_MARKER not in content:
        print(f"ERROR: Marker not found in {AUTOMATIONS_YAML}.")
        print("\n--- PASTE MANUALLY ---\n" + triggers)
        return
    start = content.index(BEGIN_MARKER)
    end = content.index(END_MARKER) + len(END_MARKER)
    content = content[:start] + f"{BEGIN_MARKER}\n{triggers}\n    {END_MARKER}" + content[end:]
    with open(AUTOMATIONS_YAML, 'w') as f:
        f.write(content)
    print(f"OK: {AUTOMATIONS_YAML} updated. Reload automations in HA.")

if __name__ == "__main__":
    main()
