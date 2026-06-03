#!/usr/bin/env python3
"""SD4 — Writes an event to event_buffer (SQLite). Replaces append_daily_evento."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.memory_db import init_db, record_event

def main():
    detalhe = sys.argv[1] if len(sys.argv) > 1 else ""
    entity_id = (sys.argv[2].strip() if len(sys.argv) > 2 else "") or None
    if not detalhe.strip():
        print("SKIP: empty detalhe"); return
    init_db()
    row_id = record_event(tipo="auto", detalhe=detalhe.strip(), entity_id=entity_id)
    print(f"OK id={row_id} detalhe={detalhe[:50]}")

if __name__ == "__main__":
    main()
