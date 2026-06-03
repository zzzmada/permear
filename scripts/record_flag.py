#!/usr/bin/env python3
"""SD5 — Writes a system flag to the DB. Replaces append_daily.py flag."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.memory_db import init_db, set_flag

def main():
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    value = sys.argv[2] if len(sys.argv) > 2 else "true"
    if not name.strip():
        print("SKIP: empty name"); return
    init_db()
    set_flag(name.strip(), value.strip())
    print(f"OK flag={name} value={value}")

if __name__ == "__main__":
    main()
