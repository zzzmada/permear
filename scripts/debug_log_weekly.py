#!/usr/bin/env python3
import sys, datetime, os

attempt = sys.argv[1] if len(sys.argv) > 1 else "?"
text = sys.argv[2] if len(sys.argv) > 2 else ""

os.makedirs('/config/logs', exist_ok=True)
with open('/config/logs/weekly_debug.log', 'a') as f:
    f.write(f"=== ATTEMPT {attempt} at {datetime.datetime.now()} ===\n{text[:2000]}\n\n")
