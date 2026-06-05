#!/usr/bin/env python3
"""
Builds the daily Sleep Consolidation prompt for the data LLM.
The prompt BODY stays PT — it instructs the LLM to produce PT briefing content
for the resident (i18n).
Outputs SUPPRESS (stdout) when the day has no events, interactions, or pending
items — cycles.yaml uses this to skip the LLM and send no message.
v5.0: includes agent automations (permear_agent.yaml), removes allowed_actions.
v8.3: empty-day suppression; light formatting instruction; infra-error exclusion.
"""
import os
import sys
import yaml
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import *
from lib.memory import load_json
from lib.agent import get_health_summary_for_prompt
from lib.memory_db import get_today_events, get_today_interactions


def load_agent_automations():
    if not os.path.exists(AGENT_YAML):
        return []
    try:
        with open(AGENT_YAML, 'r') as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, list) else []
    except (yaml.YAMLError, TypeError):
        return []


def main():
    hoje_idx = datetime.now().weekday()
    dia_nome = DAYS[hoje_idx]
    dia_pt = DAYS_PT[hoje_idx]
    data_str = datetime.now().strftime("%d/%m/%Y")

    guidelines = load_json(GUIDELINES_PATH, {})
    action = guidelines.get("action_items", {})

    pendencias = action.get("pending", [])
    sugestoes = action.get("suggestions", [])

    eventos = get_today_events()[-10:]
    n_interacoes = len(get_today_interactions())

    # Empty-day suppression: nothing to synthesize
    if not eventos and n_interacoes == 0 and not pendencias and not sugestoes:
        print("SUPPRESS")
        return

    agent_autos = load_agent_automations()
    if agent_autos:
        linhas = [f"  {i+1}. {a.get('alias','?')} (id: {a.get('id','?')})"
                  for i, a in enumerate(agent_autos)]
        autos_txt = "AUTOMACOES DO AGENTE (revise se ainda sao uteis):\n" + "\n".join(linhas)
    else:
        autos_txt = "AUTOMACOES DO AGENTE: nenhuma criada."

    eventos_txt = (
        "; ".join(f"{e.get('ts','?')[11:16]} {e.get('detalhe','?')}" for e in eventos)
        if eventos
        else "nenhum"
    )

    pendencias_txt = "; ".join(pendencias[:3]) if pendencias else "nenhuma"
    sugestoes_txt = "; ".join(sugestoes[:3]) if sugestoes else "nenhuma"

    health_line = get_health_summary_for_prompt()
    health_section = f"\n{health_line}\n" if health_line else ""

    prompt = f"""Produza o briefing residencial de {dia_pt}, {data_str}.
IMPORTANTE: Retorne APENAS o texto. Maximo 120 palavras. Sem emojis, sem markdown avancado.
Estruture em topicos curtos (3-4 linhas cada), nao em paragrafo corrido.
Exclua: erros de framework, mensagens de teste, falhas de provedor LLM, erros do proprio sistema PERMEAR.
Apenas comportamento real da casa conta.

{autos_txt}

EVENTOS DO DIA (ultimos 10): {eventos_txt}
INTERACOES HOJE: {n_interacoes} registradas.
PENDENCIAS: {pendencias_txt}
SUGESTOES DE AUTOMACAO PENDENTES: {sugestoes_txt}
{health_section}
INSTRUCOES:
1. Se ha automacoes do agente listadas, mencione-as brevemente e pergunte se ainda sao uteis.
2. Resuma o dia em 2-3 topicos. Destaque o incomum.
3. Mencione pendencias relevantes brevemente.
4. Se ha sugestoes de automacao pendentes, apresente a mais relevante.
5. Se nada especial, diga em uma frase e acrescente algo util."""

    print(prompt)


if __name__ == "__main__":
    main()
