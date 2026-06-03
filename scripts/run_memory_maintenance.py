#!/usr/bin/env python3
"""
v7.9-B — roda a manutencao de tiers (chamado na Sleep Consolidation).
v7.9-F — loop tiers->priority: delegado para lib/memory_db.update_priority_from_memory.
"""
import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.memory_db import init_db, run_tier_maintenance, update_priority_from_memory
from permear_config import MEMORY_DB_PATH


def _clean_invalid_items():
    """Remove items that entered via the ARAS error-leak bug (pre-v7.9-F fix).
    Idempotent — no-op when DB is already clean.
    """
    conn = sqlite3.connect(MEMORY_DB_PATH, timeout=10)
    cur = conn.execute("DELETE FROM memory_items WHERE key LIKE 'event:erro:%'")
    del_err = cur.rowcount
    cur = conn.execute("DELETE FROM memory_items WHERE key = 'event:to'")
    del_old = cur.rowcount
    conn.commit()
    conn.close()
    return del_err, del_old


def main():
    init_db()

    del_err, del_old = _clean_invalid_items()
    if del_err or del_old:
        print(f"cleanup: removed {del_err} error-leak item(s), {del_old} antigo-format item(s)")

    counts = run_tier_maintenance()
    print(f"OK maintenance: {counts}")

    changes = update_priority_from_memory()
    if changes:
        for ch in changes:
            print(f"priority: {ch['entity']}  {ch['from']}->{ch['to']} (memory tier={ch['tier']})")
    else:
        print("priority: no changes")


if __name__ == "__main__":
    main()
