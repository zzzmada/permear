#!/usr/bin/env python3
"""
v7.0 — Entry point for circuit breaker and daily stats.
Logic lives in lib/agent.py.

Kept as wrapper because it's called by shell_commands:
  agent_circuit_check, agent_circuit_fail, agent_circuit_success,
  agent_log_retry_success, agent_log_3fail, agent_daily_summary

Commands:
  check, fail, success, status, log_503, log_retry_success, log_3fail, daily_summary
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.agent import (
    cmd_check, cmd_fail, cmd_success, cmd_status,
    cmd_log_503, cmd_log_retry_success, cmd_log_3fail, cmd_daily_summary
)

COMMANDS = {
    "check": cmd_check,
    "fail": cmd_fail,
    "success": cmd_success,
    "status": cmd_status,
    "log_503": cmd_log_503,
    "log_retry_success": cmd_log_retry_success,
    "log_3fail": cmd_log_3fail,
    "daily_summary": cmd_daily_summary,
}


def main():
    if len(sys.argv) < 2:
        print("Usage: circuit_breaker.py {" + "|".join(COMMANDS.keys()) + "}")
        sys.exit(1)
    cmd = sys.argv[1].lower()
    if cmd in COMMANDS:
        COMMANDS[cmd]()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
