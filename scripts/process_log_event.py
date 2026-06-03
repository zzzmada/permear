#!/usr/bin/env python3
"""
v7.0 — Entry point para processamento de log events.
Logica vive em lib/logs.py.

Chamado por shell_command.process_log_event a partir da automacao
permear_error_monitor.

Usage: process_log_event.py '<component>' '<message>'
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.logs import process_event, emit


def main():
    if len(sys.argv) < 3:
        emit(True, reason="missing_args")
        return
    component = sys.argv[1]
    message = " ".join(sys.argv[2:])
    process_event(component, message)


if __name__ == "__main__":
    main()
