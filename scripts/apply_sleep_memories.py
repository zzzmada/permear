#!/usr/bin/env python3
"""SD5 — Recebe JSON array de memórias do ai_task, grava no Organic Memory DB.
v7.8-B original: gravava também no daily JSON (memorias_do_dia). Removido no SD5.
"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.memory_db import init_db, add_or_reinforce


def main():
    if len(sys.argv) < 2:
        print("Uso: apply_daily_memory.py '<json_array>'")
        sys.exit(1)
    try:
        novas = json.loads(sys.argv[1].strip())
        if not isinstance(novas, list):
            raise ValueError("esperado array JSON")
    except (ValueError, json.JSONDecodeError) as e:
        print(f"JSON inválido: {e}. Descartando.")
        sys.exit(0)
    if not novas:
        print("Lista vazia — nada a gravar.")
        sys.exit(0)
    init_db()
    new_c = reinforced = 0
    for m in novas:
        text = (m or "").strip()
        if not text:
            continue
        _, was_new, _ = add_or_reinforce(text, kind="observation", source="daily", key=None)
        if was_new:
            new_c += 1
        else:
            reinforced += 1
    print(f"OK DB: +{new_c} nova(s), {reinforced} reforçada(s)")


if __name__ == "__main__":
    main()
