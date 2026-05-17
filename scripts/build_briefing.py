#!/usr/bin/env python3
<<<<<<< HEAD
"""Daily briefing prompt (21h). Compact, includes updates and agent automations."""
import json, os, sys
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import MEMORY_DIR, AGENT_YAML, DAYS, DAYS_DISPLAY
def load_json(path, default=None):
    try:
        with open(path, 'r') as f: return json.load(f)
    except: return default if default is not None else {}
def count_agent_automations():
    try:
        import yaml
        with open(AGENT_YAML, 'r') as f: data = yaml.safe_load(f)
        return len(data) if isinstance(data, list) else 0
    except: return 0
def main():
    updates_txt = ""
    for i, arg in enumerate(sys.argv):
        if arg == "--updates" and i + 1 < len(sys.argv): updates_txt = sys.argv[i + 1]
    idx = datetime.now().weekday()
=======
"""
Builds the daily briefing prompt for the LLM agent.
v5.0: includes agent-created automations (agent_automations.yaml), removes allowed_actions.
v7.0: injects health summary line.
"""
import os
import sys
import yaml
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import *
from lib.memory import load_json
from lib.agent import get_health_summary_for_prompt


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
    day_display = DAYS_DISPLAY[idx]
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
    date_str = datetime.now().strftime("%Y-%m-%d")
    soul = load_json(os.path.join(MEMORY_DIR, "soul.json"))
    insights = load_json(os.path.join(MEMORY_DIR, "insights.json"))
<<<<<<< HEAD
    daily = load_json(os.path.join(MEMORY_DIR, "daily", f"{DAYS[idx]}.json"),
                      {"events": [], "interactions": [], "daily_memories": []})
    if daily.get("date") != date_str:
        daily = {"events": [], "interactions": [], "daily_memories": []}
    events = daily.get("events", [])
    interactions = daily.get("interactions", [])
    memories = daily.get("daily_memories", [])
    events_txt = f"{len(events)} events"
    if events:
        events_txt += ": " + ", ".join(f"{e.get('time','?')}-{e.get('detail','?')}" for e in events[-10:])
    memories_txt = ""
    if memories:
        memories_txt = "Memories learned today: " + "; ".join(memories[:10])
        memories_txt += "\n(Note: extracted during earlier pre-briefings.)"
    pending = insights.get("pending_items", [])
    pending_txt = "Open items: " + "; ".join(pending) if pending else ""
    auto_count = count_agent_automations()
    auto_txt = f"Agent automations: {auto_count} active." if auto_count > 0 else ""
    updates_section = f"HA UPDATES:\n{updates_txt}" if updates_txt and "up to date" not in updates_txt.lower() else ""
    prompt = f"""You are {soul.get('name', 'Assistant')}, a residential assistant and system caretaker.
TASK: Daily briefing for {DAYS_DISPLAY[idx]}, {date_str}. Telegram message. Max 120 words. No emojis, no markdown.
TODAY: {events_txt}
Interactions: {len(interactions)}
{memories_txt}
{pending_txt}
{auto_txt}
{updates_section}
STRUCTURE:
1. One or two sentences about the day — what happened, anything unusual.
2. What the system learned today (memories), in one sentence.
3. If there are HA updates available, mention them.
4. Skip anything routine.
Tone: direct, like a brief shift report."""
    print(prompt)
=======
    daily = load_json(
        os.path.join(MEMORY_DIR, "daily", f"{day_key}.json"),
        {"events": [], "interactions": [], "daily_memories": []},
    )

    today = datetime.now().strftime("%Y-%m-%d")
    if daily.get("date") != today:
        daily = {"events": [], "interactions": [], "daily_memories": []}

    agent_autos = load_agent_automations()
    if agent_autos:
        lines = [f"  {i+1}. {a.get('alias','?')} (id: {a.get('id','?')})"
                 for i, a in enumerate(agent_autos)]
        autos_txt = "AGENT AUTOMATIONS (review if still useful):\n" + "\n".join(lines)
    else:
        autos_txt = "AGENT AUTOMATIONS: none created."

    events = daily.get("events", [])[-10:]
    events_txt = (
        "; ".join(f"{e.get('time','?')} {e.get('detail','?')}" for e in events)
        if events
        else "none"
    )

    n_interactions = len(daily.get("interactions", []))

    pending = insights.get("pending", [])
    pending_txt = "; ".join(pending[:3]) if pending else "none"

    memories_txt = "; ".join(daily.get("daily_memories", [])) or "none"

    suggestions = insights.get("automation_suggestions", [])
    suggestions_txt = "; ".join(suggestions[:3]) if suggestions else "none"

    health_line = get_health_summary_for_prompt()
    health_section = f"\n{health_line}\n" if health_line else ""

    prompt = f"""You are {soul.get('name', 'PERMEAR')}, the household AI assistant.

TASK: Daily briefing for {day_display}, {date_str}.
IMPORTANT: Return ONLY the text. Maximum 120 words. No emojis, no markdown.

{autos_txt}

EVENTS TODAY (last 10): {events_txt}
INTERACTIONS TODAY: {n_interactions} recorded.
DAILY MEMORIES: {memories_txt}
PENDING ITEMS: {pending_txt}
AUTOMATION SUGGESTIONS PENDING: {suggestions_txt}
{health_section}
INSTRUCTIONS:
1. If there are agent automations listed, briefly mention them and ask if still useful.
2. Summarize the day in 2-3 sentences. Highlight the unusual.
3. Mention relevant pending items briefly.
4. If there are pending automation suggestions, present the most relevant.
5. If nothing special, say so in one sentence and add something useful."""

    print(prompt)


>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
if __name__ == "__main__":
    main()
