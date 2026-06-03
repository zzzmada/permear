#!/usr/bin/env python3
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import *
from lib.memory import load_json

guidelines = load_json(GUIDELINES_PATH, {})

print(json.dumps({'residents': guidelines.get('residents', {}), 'action_items': guidelines.get('action_items', {})}, ensure_ascii=False))
