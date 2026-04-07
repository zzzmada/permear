#!/usr/bin/env python3
"""
Generate the trigger block for the event buffer automation from
monitored_entities.json. Reads the 'events' field of each entity
and outputs YAML triggers between markers in the automation file.

Run manually after editing events in monitored_entities.json:
  python3 /config/scripts/generate_buffer_events.py
Then reload automations in HA (Developer Tools → YAML → Automations).

The automation file must contain these markers:
  # [BEGIN buffer_events triggers — generated]
  ...triggers here...
  # [END buffer_events triggers — generated]
"""
import json, os, sys

MONITORED_PATH = "/config/memory/monitored_entities.json"
AUTOMATION_PATH = "/config/automations/permear.yaml"  # adjust to your file

BEGIN_MARKER = "# [BEGIN buffer_events triggers — generated]"
END_MARKER = "# [END buffer_events triggers — generated]"

def load_monitored():
    with open(MONITORED_PATH, 'r') as f:
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
                    lines.append(f'      to: "{ev["to"]}"')
                if "from" in ev:
                    lines.append(f'      from: "{ev["from"]}"')
                if "for" in ev:
                    lines.append(f'      for: "{ev["for"]}"')
                if ev_id:
                    lines.append(f'      id: "{ev_id}"')

            elif trigger_type == "numeric_state":
                lines.append(f"    - platform: numeric_state")
                lines.append(f"      entity_id: {entity_id}")
                if "above" in ev:
                    lines.append(f"      above: {ev['above']}")
                if "below" in ev:
                    lines.append(f"      below: {ev['below']}")
                if ev_id:
                    lines.append(f'      id: "{ev_id}"')

    return "\n".join(lines)

def update_automation_file(new_triggers_yaml):
    with open(AUTOMATION_PATH, 'r') as f:
        content = f.read()

    if BEGIN_MARKER not in content:
        print(f"ERROR: Marker '{BEGIN_MARKER}' not found in {AUTOMATION_PATH}.")
        print("Add the markers manually around the trigger list in your buffer events automation.")
        return False

    start = content.index(BEGIN_MARKER)
    end = content.index(END_MARKER) + len(END_MARKER)

    new_block = f"{BEGIN_MARKER}\n{new_triggers_yaml}\n    {END_MARKER}"
    content = content[:start] + new_block + content[end:]

    with open(AUTOMATION_PATH, 'w') as f:
        f.write(content)
    return True

def main():
    if not os.path.exists(MONITORED_PATH):
        print(f"ERROR: {MONITORED_PATH} not found.")
        sys.exit(1)

    data = load_monitored()
    entities = data.get("entities", [])

    triggers_yaml = build_triggers_yaml(entities)
    if not triggers_yaml.strip():
        print("WARNING: No events defined in monitored_entities.json.")
        sys.exit(0)

    trigger_count = triggers_yaml.count("- platform:")
    print(f"Generated {trigger_count} triggers.")

    if update_automation_file(triggers_yaml):
        print(f"OK: {AUTOMATION_PATH} updated. Reload automations in HA to apply.")
    else:
        print("\n--- TRIGGERS YAML (paste manually) ---")
        print(triggers_yaml)

if __name__ == "__main__":
    main()
