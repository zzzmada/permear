#!/usr/bin/env python3
"""
Briefing diario fallback — sem Gemini.
Le daily/<dia_atual>.json + guidelines.json (action_items).
Imprime texto PT-BR no stdout.
"""
import os
import subprocess
import sys
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import MEMORY_DIR, DAYS, DAYS_PT, GUIDELINES_PATH
from lib.memory import load_json
from lib.memory_db import count_today_events, get_today_interactions


def get_gemini_summary():
    try:
        r = subprocess.run(
            ["python3", "/config/scripts/circuit_breaker.py", "daily_summary"],
            capture_output=True, text=True, timeout=3
        )
        return r.stdout.strip()
    except Exception:
        return ""


def main():
    hoje_idx = datetime.now().weekday()
    dia_pt = DAYS_PT[hoje_idx]
    data_str = datetime.now().strftime("%d/%m/%Y")

    # SD4: contagens do DB
    guidelines = load_json(GUIDELINES_PATH, {})
    action = guidelines.get("action_items", {})

    n_eventos = count_today_events()
    n_interacoes = len(get_today_interactions())
    pendencias = action.get("pending", [])

    partes = [f"Briefing de {dia_pt}, {data_str}."]
    partes.append(f"Hoje foram registrados {n_eventos} eventos e {n_interacoes} interacoes.")

    if pendencias:
        partes.append(f"Pendencias em aberto: {pendencias[0]}")
        if len(pendencias) > 1:
            partes.append(f"Tambem ha: {pendencias[1]}")

    partes.append("Briefing completo indisponivel agora — Gemini retornou erro. Tente perguntar diretamente caso queira detalhes.")

    gemini_health = get_gemini_summary()
    if gemini_health:
        partes.append(gemini_health)

    print(" ".join(partes))


if __name__ == "__main__":
    main()
