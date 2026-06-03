#!/usr/bin/env python3
"""v7.9-B — grava um evento EMITIDO no Organic Memory DB (kind=observation)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.memory_db import init_db, add_or_reinforce

def main():
    content = sys.argv[1] if len(sys.argv) > 1 else ""
    key = sys.argv[2] if len(sys.argv) > 2 else None
    if not content.strip():
        print("SKIP: empty content"); return
    init_db()
    _id, was_new, via = add_or_reinforce(
        content.strip(), kind="observation", source="heartbeat",
        key=(key.strip() or None) if key else None
    )
    print(f"OK id={_id} new={was_new} via={via}")

if __name__ == "__main__":
    main()
