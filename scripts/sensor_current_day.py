#!/usr/bin/env python3
"""Sensor that exposes today's daily memory file as JSON attributes."""
from datetime import datetime
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import *
from lib.memory import load_json

day = DAYS[datetime.now().weekday()]
path = os.path.join(DAILY_DIR, f'{day}.json')
today = datetime.now().strftime('%Y-%m-%d')
empty = {'events': [], 'interactions': [], 'daily_memories': []}

d = load_json(path)
if d.get('date') == today:
    print(json.dumps(d, ensure_ascii=False))
else:
    print(json.dumps(empty, ensure_ascii=False))
