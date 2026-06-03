#!/usr/bin/env python3
"""SD23-B — Writes a Telegram/voice message to the DB (kind=observation, source='interaction')."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.memory_db import init_db, add_or_reinforce

def main():
    canal = sys.argv[1] if len(sys.argv) > 1 else "desconhecido"
    content = sys.argv[2] if len(sys.argv) > 2 else ""
    if not content.strip():
        print("SKIP: empty content"); return
    init_db()
    _id, was_new, via = add_or_reinforce(
        content.strip(), kind="observation", source="interaction",
        metadata={"canal": canal}
    )
    print(f"OK id={_id} new={was_new} via={via} canal={canal}")

if __name__ == "__main__":
    main()
