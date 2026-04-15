#!/usr/bin/env python3
"""Build the pre-briefing proactive evaluation prompt. v5.4: SELF_ERRORS awareness."""
import json, os, sys
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import MEMORY_DIR, ENTITIES_PATH, TOKEN_PATH, HA_URL, DAYS

def load_json(path, default=None):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}

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
            state = data.get("state", "unavailable")
            unit = data.get("attributes", {}).get("unit_of_measurement", "")
            return f"{state}{' ' + unit if unit else ''}"
    except (URLError, Exception):
        return "unavailable"

def build_house_state(token):
    monitored = load_json(ENTITIES_PATH, {"entities": []})
    entities = [e for e in monitored.get("entities", []) if e.get("monitor", False)]
    if not entities or not token:
        return "House state: not available."
    lines = []
    for ent in entities[:30]:
        eid = ent.get("entity_id", "")
        name = ent.get("friendly_name", eid)
        state = get_entity_state(eid, token)
        lines.append(f"  {name}: {state}")
    return "\n".join(lines)

def main():
    health_txt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    idx = datetime.now().weekday()
    timestamp = datetime.now().strftime("%H:%M")
    token = load_token()

    soul = load_json(os.path.join(MEMORY_DIR, "soul.json"))
    users = load_json(os.path.join(MEMORY_DIR, "users.json"))
    insights = load_json(os.path.join(MEMORY_DIR, "insights.json"))
    daily = load_json(os.path.join(MEMORY_DIR, "daily", f"{DAYS[idx]}.json"),
                      {"events": [], "interactions": [], "daily_memories": []})

    today = datetime.now().strftime("%Y-%m-%d")
    if daily.get("date") != today:
        daily = {"events": [], "interactions": [], "daily_memories": []}

    house_state = build_house_state(token)

    events = daily.get("events", [])
    recent_alerts = [i.get("summary", "")[:50] for i in daily.get("interactions", [])[-5:]
                     if i.get("channel") == "prebriefing"]

    patterns = insights.get("detected_patterns", [])
    patterns_txt = "; ".join(patterns[-10:]) if patterns else "None"

    restrictions = []
    for ud in users.values():
        restrictions.extend(ud.get("restrictions", []))
    restrictions_txt = "; ".join(restrictions) if restrictions else "None"

    health_section = ""
    has_self_errors = False
    if health_txt and health_txt != "HEALTH: OK":
        health_section = f"\nSYSTEM HEALTH:\n{health_txt}"
        has_self_errors = "SELF_ERRORS" in health_txt

    self_errors_instruction = ""
    if has_self_errors:
        self_errors_instruction = """
7. SELF_ERRORS are failures in YOUR OWN actions (Telegram, conversation, automation, shell_command). These were caused by something YOU did. Report immediately with:
   - What you think went wrong
   - What your last action was (check today's interactions)
   - A suggested fix
   Do NOT dismiss SELF_ERRORS as routine HA issues."""

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
5. ERRORS in system health (external issues): alert if critical, suggest fix.
6. Prefer SILENCE when in doubt.{self_errors_instruction}

RESPOND: the message OR SILENCE. Nothing else."""

    print(prompt)

if __name__ == "__main__":
    main()
