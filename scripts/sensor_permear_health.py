#!/usr/bin/env python3
"""
v7.7 — PERMEAR health sensor. States: tudo_ok | fallback_ativo.

Simplified after the ai_task migration (v7.7-llm): the circuit breaker is no
longer fed by any active point. Reflects what is actually observed:
fallbacks to the secondary provider (Gemini) via agent_log_fallback.

NOTE: state values and the `resumo` attribute stay PT — they are user-facing
(dashboard). See CLAUDE.md rule 22.
"""
import sys
import os
import json
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.memory import load_json
from permear_config import AGENT_CIRCUIT_PATH, ARCHIVED_ERRORS_PATH


def main():
    circuit = load_json(AGENT_CIRCUIT_PATH, default={
        "daily_stats": {},
        "last_fallback_at": None,
    })

    today = datetime.now().strftime("%Y-%m-%d")
    raw_stats = circuit.get("daily_stats", {})
    stats = raw_stats if raw_stats.get("date") == today else {}

    fallbacks = stats.get("fallbacks_gemini", 0)
    archived = load_json(ARCHIVED_ERRORS_PATH, default={"errors": {}})
    archived_count = len(archived.get("errors", {}))

    if fallbacks >= 1:
        state = "fallback_ativo"
        resumo = "Operando com provedor secundario (Gemini) hoje."
    else:
        state = "tudo_ok"
        resumo = "Funcionando normalmente"

    out = {
        "state": state,
        "resumo": resumo,
        "fallbacks_gemini_hoje": fallbacks,
        "ultimo_fallback_em": circuit.get("last_fallback_at"),
        "erros_silenciados_ativos": archived_count,
    }

    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
