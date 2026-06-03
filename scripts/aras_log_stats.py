#!/usr/bin/env python3
"""Accumulates ARAS Filter statistics for the day (written by Heartbeat)."""
import sys
import os
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import MEMORY_DIR
from lib.memory import locked_update

ATTENTION_PATH = os.path.join(MEMORY_DIR, "aras_stats.json")


def main():
    if len(sys.argv) < 6:
        print("ERR: usage: aras_log_stats.py total emit gray suppress llm_calls [emit_threshold]")
        sys.exit(1)
    total, emit, gray, suppress, llm = (int(x) for x in sys.argv[1:6])
    # v7.9-C: optional 6th arg — current dynamic threshold (not accumulated, overwrites)
    threshold = int(sys.argv[6]) if len(sys.argv) > 6 else None
    today = datetime.now().strftime("%Y-%m-%d")
    with locked_update(ATTENTION_PATH, default={}) as s:
        if s.get("data") != today:
            s.clear()
            s.update({"data": today, "total": 0, "emit": 0,
                      "gray": 0, "suppress": 0, "llm_calls": 0})
        s["total"] += total
        s["emit"] += emit
        s["gray"] += gray
        s["suppress"] += suppress
        s["llm_calls"] += llm
        if threshold is not None:
            s["emit_threshold"] = threshold  # last seen value (not accumulated)
    print("OK")


if __name__ == "__main__":
    main()
