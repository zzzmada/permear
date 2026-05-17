#!/usr/bin/env python3
<<<<<<< HEAD
"""Pre-briefing proactive evaluation. v5.4: SELF_ERRORS awareness."""
import json, os, sys
=======
"""
Builds the proactive pre-briefing prompt.
v5.0: reads monitored_entities.json via REST API, includes health summary and agent automations.
v7.0: injects agent health line.
"""
import json
import os
import sys
import yaml
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
<<<<<<< HEAD
from permear_config import MEMORY_DIR, ENTITIES_PATH, TOKEN_PATH, HA_URL, DAYS
def load_json(path, default=None):
    try:
        with open(path, 'r') as f: return json.load(f)
    except: return default if default is not None else {}
def load_token():
    try:
        with open(TOKEN_PATH, 'r') as f: return f.read().strip()
    except: return None
=======
from permear_config import *
from lib.memory import load_json
from lib.agent import get_health_summary_for_prompt


def load_token():
    try:
        with open(TOKEN_PATH, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
def get_entity_state(entity_id, token):
    try:
        req = Request(f"{HA_URL}/api/states/{entity_id}",
                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            state = data.get("state", "unavailable")
<<<<<<< HEAD
            unit = data.get("attributes", {}).get("unit_of_measurement", "")
            return f"{state}{' ' + unit if unit else ''}"
    except: return "unavailable"
def build_house_state(token):
    monitored = load_json(ENTITIES_PATH, {"entities": []})
    entities = [e for e in monitored.get("entities", []) if e.get("monitor", False)]
    if not entities or not token: return "House state: not available."
    lines = []
    for ent in entities[:30]:
        name = ent.get("friendly_name", ent.get("entity_id", "?"))
        state = get_entity_state(ent.get("entity_id", ""), token)
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
=======
            attrs = data.get("attributes", {})
            unit = attrs.get("unit_of_measurement", "")
            return f"{state}{' ' + unit if unit else ''}"
    except URLError:
        return "unavailable"


def build_house_state(token):
    monitored = load_json(ENTITIES_PATH, {"entities": []})
    entities = [e for e in monitored.get("entities", []) if e.get("monitor", False)]

    if not entities:
        return "State unavailable (monitored_entities.json empty or missing)."

    lines = []
    for e in entities[:30]:  # limit for RPi4 performance
        entity_id = e.get("entity_id", "")
        friendly = e.get("friendly_name", entity_id)
        state = get_entity_state(entity_id, token)
        lines.append(f"  {friendly}: {state}")

    return "\n".join(lines)


def load_agent_automations():
    if not os.path.exists(AGENT_YAML):
        return []
    try:
        with open(AGENT_YAML, 'r') as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, list) else []
    except (yaml.YAMLError, TypeError):
        return []


def main():
    idx = datetime.now().weekday()
    day_key = DAYS[idx]
    time_str = datetime.now().strftime("%H:%M")

    soul = load_json(os.path.join(MEMORY_DIR, "soul.json"))
    users = load_json(os.path.join(MEMORY_DIR, "users.json"))
    insights = load_json(os.path.join(MEMORY_DIR, "insights.json"))
    daily = load_json(os.path.join(MEMORY_DIR, "daily", f"{day_key}.json"),
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
                      {"events": [], "interactions": [], "daily_memories": []})
    today = datetime.now().strftime("%Y-%m-%d")
    if daily.get("date") != today:
        daily = {"events": [], "interactions": [], "daily_memories": []}
<<<<<<< HEAD
    house_state = build_house_state(token)
    events = daily.get("events", [])
    recent_alerts = [i.get("summary", "")[:50] for i in daily.get("interactions", [])[-5:]
                     if i.get("channel") == "prebriefing"]
    patterns = insights.get("detected_patterns", [])
    patterns_txt = "; ".join(patterns[-10:]) if patterns else "None"
    restrictions = []
    for ud in users.values(): restrictions.extend(ud.get("restrictions", []))
    restrictions_txt = "; ".join(restrictions) if restrictions else "None"
    health_section = ""
    has_self_errors = False
    if health_txt and health_txt != "HEALTH: OK":
        health_section = f"\nSYSTEM HEALTH:\n{health_txt}"
        has_self_errors = "SELF_ERRORS" in health_txt
    self_errors_instruction = ""
    if has_self_errors:
        self_errors_instruction = """
7. SELF_ERRORS are failures in YOUR OWN actions (Telegram, conversation, automation, shell_command).
   Report immediately: what went wrong, what your last action was, suggested fix.
   Do NOT dismiss as routine."""
    prompt = f"""You are {soul.get('name', 'Assistant')}, residential assistant and system caretaker. Time: {timestamp}.
HOUSE STATE:
{house_state}
{health_section}
Today's events: {len(events)}. Recent alerts sent: {', '.join(recent_alerts) if recent_alerts else 'none'}
Known patterns: {patterns_txt}
User restrictions: {restrictions_txt}
RULES:
1. RELEVANT issue → short message (max 2 sentences).
2. Nothing relevant → respond EXACTLY: SILENCE
3. Never alert about known patterns or user restrictions.
4. Never repeat an alert already sent today.
5. ERRORS in system health: alert if critical, suggest fix.
6. Prefer SILENCE when in doubt.{self_errors_instruction}
RESPOND: the message OR SILENCE. Nothing else."""
    print(prompt)
=======

    health_summary = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "HEALTH: OK"
    has_self_errors = "SELF_ERRORS" in health_summary

    token = load_token()
    if token:
        house_state = build_house_state(token)
    else:
        house_state = "Token unavailable."

    agent_autos = load_agent_automations()
    if agent_autos:
        autos_txt = "\n".join(f"  - {a.get('alias','?')} (id: {a.get('id','?')})" for a in agent_autos)
    else:
        autos_txt = "  No automations created by the agent."

    if daily["events"]:
        events_txt = "".join(f"  {e.get('time','?')} - {e.get('detail','?')}\n" for e in daily["events"])
    else:
        events_txt = "  No events so far.\n"

    if daily["interactions"]:
        interactions_txt = "".join(
            f"  {i.get('time','?')} ({i.get('channel','?')}): {i.get('summary','?')}\n"
            for i in daily["interactions"]
        )
    else:
        interactions_txt = "  No interactions so far.\n"

    if insights.get("detected_patterns"):
        patterns_txt = "".join(f"  - {p}\n" for p in insights["detected_patterns"])
    else:
        patterns_txt = "  No patterns recorded.\n"

    # Primary user is first key in users dict
    primary_user_key = list(users.keys())[0] if users else None
    primary_user = users.get(primary_user_key, {}) if primary_user_key else {}
    restrictions = primary_user.get("restrictions", [])
    restrictions_txt = "\n".join(f"  - {r}" for r in restrictions) if restrictions else "  None."

    agent_health_line = get_health_summary_for_prompt()
    agent_health_section = f"\nAGENT HEALTH:\n{agent_health_line}\n" if agent_health_line else ""

    self_errors_rule = ""
    if has_self_errors:
        self_errors_rule = """
SELF_ERRORS are failures in YOUR OWN actions (Telegram, conversation, automation, shell_command). These were caused by something YOU did. Report immediately with:
- What you think went wrong
- What your last action was (check today's interactions)
- A suggested fix
Do NOT dismiss SELF_ERRORS as routine HA issues.
"""

    user_label = primary_user_key.capitalize() if primary_user_key else "the user"

    prompt = f"""You are {soul.get('name', 'PERMEAR')}, the household AI assistant.

TASK: Assess the current state of the house and decide whether to contact {user_label} now ({time_str}).

HA SYSTEM HEALTH:
{health_summary}
{agent_health_section}
CURRENT HOUSE STATE:
{house_state}

AGENT-CREATED AUTOMATIONS:
{autos_txt}

EVENTS TODAY SO FAR:
{events_txt}
INTERACTIONS TODAY:
{interactions_txt}
KNOWN PATTERNS (insights - what you already know):
{patterns_txt}
USER RESTRICTIONS (things they already said NOT to alert about):
{restrictions_txt}

DECISION RULES:{self_errors_rule}
1. If there is something RELEVANT that {user_label} probably doesn't know and would benefit from knowing now, write a short message (max 2 sentences) - alert, question or observation.
2. If NOTHING relevant or the situation is already known/expected per the patterns, respond EXACTLY: SILENCE
3. NEVER alert about things already in the known patterns as normal.
4. NEVER alert about things in the user restrictions.
5. Critical HA errors (ERRORS in health summary): notify immediately with suggested fix.
6. New updates available: mention only in the 21h briefing, never interrupt the day.
7. New Zigbee devices detected: ask if {user_label} wants to name and configure.
8. If you already sent an alert about the same topic today (check interactions), DON'T repeat.
9. Prefer SILENCE when in doubt. Less is more.

RESPOND WITH ONLY: the short message OR the word SILENCE. Nothing more."""

    print(prompt)


>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
if __name__ == "__main__":
    main()
