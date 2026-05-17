#!/usr/bin/env python3
"""v7.1-I — Logs use of secondary AI Task provider as fallback."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.agent import increment_fallback_count


def main():
    count = increment_fallback_count()
    print(f"FALLBACK_SECONDARY #{count}")


if __name__ == "__main__":
    main()
