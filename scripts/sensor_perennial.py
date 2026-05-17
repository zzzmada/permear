#!/usr/bin/env python3
"""Sensor that exposes perennial memory files (soul, users, insights) as JSON attributes."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import *
from lib.memory import load_json

soul = load_json(os.path.join(MEMORY_DIR, 'soul.json'))
users = load_json(os.path.join(MEMORY_DIR, 'users.json'))
insights = load_json(os.path.join(MEMORY_DIR, 'insights.json'))

print(json.dumps({'soul': soul, 'users': users, 'insights': insights}, ensure_ascii=False))
