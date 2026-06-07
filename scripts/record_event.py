#!/usr/bin/env python3
"""SD4 — Writes an event to event_buffer (SQLite). Replaces append_daily_evento."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.memory_db import init_db, record_event, append_event_log
from datetime import datetime

def main():
    detalhe = sys.argv[1] if len(sys.argv) > 1 else ""
    entity_id = (sys.argv[2].strip() if len(sys.argv) > 2 else "") or None
    metadata_raw = sys.argv[3] if len(sys.argv) > 3 else '{}'
    if not detalhe.strip():
        print("SKIP: empty detalhe"); return
    try:
        json.loads(metadata_raw)
        metadata = metadata_raw
    except (json.JSONDecodeError, ValueError):
        print(f"WARNING: invalid metadata JSON, using '{{}}'", file=sys.stderr)
        metadata = '{}'
    init_db()
    now = datetime.now().isoformat()
    row_id = record_event(tipo="auto", detalhe=detalhe.strip(), entity_id=entity_id, metadata=metadata, ts=now)
    # v8.5-eventlog: grava mesma ocorrência no log histórico (mesmo ts, mesma metadata)
    try:
        append_event_log(ts=now, entity_id=entity_id, detalhe=detalhe.strip(), metadata=metadata)
    except Exception as e:
        print(f"WARNING: event_log write failed ({e}) — buffer OK", file=sys.stderr)
    print(f"OK id={row_id} detalhe={detalhe[:50]}")

if __name__ == "__main__":
    main()
