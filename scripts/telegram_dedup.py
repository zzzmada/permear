#!/usr/bin/env python3
"""Structural dedup guard for the Telegram message handler.
Checks whether a message_id was already processed today.
Outputs NEW or DUP to stdout.
Flag key uses daily_ prefix — auto-cleaned by reset_daily_flags() at midnight.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.memory_db import init_db, get_flag, set_flag


def main():
    mid = sys.argv[1] if len(sys.argv) > 1 else ""
    if not mid or mid == "0":
        print("NEW"); return
    init_db()
    key = f"daily_telegram_mid_{mid}"
    if get_flag(key):
        print("DUP"); return
    set_flag(key, "1")
    print("NEW")


if __name__ == "__main__":
    main()
