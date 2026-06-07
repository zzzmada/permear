#!/usr/bin/env python3
"""
v7.1-F.2 — Reads monitored_entities.json and returns a formatted list
for injection into ai_task prompts.

Output: multi-line string grouped by domain (monitor=True only).

Usage:
  get_monitored_entities_text.py                           # all domains
  get_monitored_entities_text.py light climate             # subset of domains
  get_monitored_entities_text.py light switch climate sensor binary_sensor
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.memory import load_json
from permear_config import ENTITIES_PATH

# Entities whose entity_id is not descriptive for a prompt (name == id)
# e.g. switch.sacada, switch.painel (no useful friendly_name)
_SKIP_WHEN_NO_NAME = True


def main():
    data = load_json(ENTITIES_PATH, default={"entities": []})
    entities = data.get("entities", [])

    monitored = [e for e in entities if e.get("monitor", False)]

    if not monitored:
        print("(no monitored entities at the moment)")
        return

    # Optional domain filter via argv (each arg = one domain)
    domain_filter = set(d.lower() for d in sys.argv[1:]) if len(sys.argv) > 1 else None

    by_domain = {}
    for e in monitored:
        eid = e.get("entity_id", "")
        domain = eid.split(".")[0] if "." in eid else "outros"

        if domain_filter and domain not in domain_filter:
            continue

        fname = e.get("friendly_name", "").strip()

        # Skip entities where friendly_name == entity_id (no descriptive name)
        if _SKIP_WHEN_NO_NAME and (not fname or fname == eid):
            continue

        if domain not in by_domain:
            by_domain[domain] = []

        # Format: "entity_id (Friendly Name)" or just "entity_id" if the name is obvious
        eid_base = eid.split(".", 1)[1].replace("_", " ") if "." in eid else eid
        if fname.lower() != eid_base.lower():
            line = f"  {eid} ({fname})"
        else:
            line = f"  {eid}"
        by_domain[domain].append((eid, line))

    if not by_domain:
        print("(no entities in the requested domain(s))")
        return

    lines = []
    for domain in sorted(by_domain.keys()):
        items = sorted(by_domain[domain], key=lambda x: x[0])
        lines.append(f"{domain.upper()}:")
        for _, text in items:
            lines.append(text)
        lines.append("")

    print("\n".join(lines).rstrip())


if __name__ == "__main__":
    main()
