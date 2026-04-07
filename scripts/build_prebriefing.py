#!/usr/bin/env python3
"""
Build the pre-briefing proactive evaluation prompt.
v5.0: Reads monitored_entities.json for dynamic house state.
      Receives HA health summary as argument from automation.
      Queries entity states via REST API.
"""
import json, os, sys
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError

MEMORY_DIR = "/config/memory"
ENTITIES_PATH = "/config/memory/monitored_entities.json"
TOKEN_PATH = "/config/.permear_token"
HA_URL = "http://localhost:8123"
DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

def load_json(path, default=None):
    if default is None:
        default = {}
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def load_token():
    try:
        with open(TOKEN_PATH, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return None

def get_entity_state(entity_id, token):
    url = f"{HA_URL}/api/states/{entity_id}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return data.get("state", "unknown")
    except (URLError, Exception):
        return "unavailable"

def build_house_state(token):
    """Build compact house state from monitored entities."""
    monitored = load_json(ENTITIES_PATH, {"entities": []})
    entities = monitored.get("entities", [])

    if not entities or not token:
        return "House state: not available (no monitored entities or no token)."

    lines = []
    for ent in entities:
        eid = ent.get("entity_id", "")
        name = ent.get("friendly_name", eid)
        state = get_entity_state(eid, token)
        if state not in ["unavailable", "unknown"]:
            lines.append(f"{name}: {state}")
    
    return "\n".join(lines) if lines else "No entity states available."

def main():
    # Health summary passed as first positional argument
    health_txt = ""
    if len(sys.argv) > 1:
        health_txt = " ".join(sys.argv[1:])

    idx = datetime.now().weekday()
    day_name = DAYS[idx]
    timestamp = datetime.now().strftime("%H:%M")
    token = load_token()

    soul = load_json(os.path.join(MEMORY_DIR, "soul.json"))
    users = load_json(os.path.join(MEMORY_DIR, "users.json"))
    insights = load_json(os.path.join(MEMORY_DIR, "insights.json"))
    daily = load_json(os.path.join(MEMORY_DIR, "daily", f"{day_name}.json"),
                      {"events": [], "interactions": [], "daily_memories": []})

    today = datetime.now().strftime("%Y-%m-%d")
    if daily.get("date") != today:
        daily = {"events": [], "interactions": [], "daily_memories": []}

    house_state = build_house_state(token)

    # Compact events
    events = daily.get("events", [])
    events_txt = ""
    if events:
        for e in events[-5:]:
            events_txt += f"  {e.get('time','?')} {e.get('detail','?')}\n"

    # Compact interactions (to detect if same alert already sent)
    interactions = daily.get("interactions", [])
    recent_alerts = [i.get("summary", "")[:50] for i in interactions[-5:]
                     if i.get("channel") == "prebriefing"]

    # Patterns
    patterns = insights.get("detected_patterns", [])
    patterns_txt = "; ".join(patterns[-10:]) if patterns else "None"

    # Restrictions from all users
    restrictions = []
    for uk, ud in users.items():
        for r in ud.get("restrictions", []):
            restrictions.append(r)
    restrictions_txt = "; ".join(restrictions) if restrictions else "None"

    # Health
    health_section = f"\nSYSTEM HEALTH:\n{health_txt}" if health_txt and health_txt != "HEALTH: OK" else ""

    prompt = f"""You are {soul.get('name', 'Assistant')}, residential assistant and system caretaker. Time: {timestamp}.

HOUSE STATE:
{house_state}
{health_section}

Today's events: {len(events)}. Recent alerts sent: {', '.join(recent_alerts) if recent_alerts else 'none'}
Known patterns: {patterns_txt}
User restrictions: {restrictions_txt}

RULES:
1. RELEVANT issue the user doesn't know about → short message (max 2 sentences).
2. Nothing relevant → respond EXACTLY: SILENCE
3. Never alert about known patterns or user restrictions.
4. Never repeat an alert already sent today (check recent alerts).
5. System health issues (errors, unavailable entities): alert if critical.
6. Prefer SILENCE when in doubt.

RESPOND: the message OR SILENCE. Nothing else."""

    print(prompt)

if __name__ == "__main__":
    main()
