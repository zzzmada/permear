#!/usr/bin/env python3
"""SD5 — Current-day sensor. Everything from the DB; no JSON files."""
from datetime import datetime
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.memory_db import get_today_events, get_today_interactions, get_flag

hoje = datetime.now().strftime('%Y-%m-%d')

print(json.dumps({
    "data": hoje,
    "eventos": get_today_events(),
    "interacoes": get_today_interactions(),
    "memorias_do_dia": [],
    "boletim_disparado": get_flag('daily_boletim_disparado', 'false') == 'true',
    "briefing_enviado": get_flag('daily_briefing_enviado', 'false') == 'true',
}, ensure_ascii=False))
