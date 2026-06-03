#!/usr/bin/env python3
"""
Builds the prompt for Systems Consolidation (weekly compile).
The prompt BODY stays PT — it instructs the LLM to produce PT content and
carries a PT-keyed JSON contract consumed by systems_compile (apply_insights_v2).
v5.1: guidelines summarized inline (was ~4KB serialized; full validation in
Python post-response).
v5.0: proposed_automations (replaces proposed_actions), removes allowed_actions.
"""

DIRETRIZES_RESUMO = """DIRETRIZES (resumo — regras completas validadas pelo Python pós-resposta):
- guidelines.json residents: config estável dos moradores (v8). Aprendizado vai para o banco, não aqui.
- guidelines.json action_items: pending (pendencias acionaveis, max 20, remover apos 30 dias); suggestions (sugestoes de automacao, max 10).
- NUNCA duplicar info entre arquivos. Antes de adicionar, verificar se ja existe."""
import json
import os
import sys
import yaml
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import *
from lib.memory import load_json
from lib.memory_db import get_recent_memories, get_recent_interactions


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
    guidelines = load_json(GUIDELINES_PATH, {})
    action_items = guidelines.get("action_items", {})
    residents = guidelines.get("residents", {})

    agent_autos = load_agent_automations()
    if agent_autos:
        autos_list = [{"alias": a.get("alias","?"), "id": a.get("id","?")} for a in agent_autos]
        autos_txt = json.dumps(autos_list, ensure_ascii=False)
    else:
        autos_txt = "[]"

    # SD5: daily JSONs eliminados — contexto vem inteiramente do banco de memória
    semana_txt = ""

    memorias_semana = get_recent_memories(days=7, source='daily')
    if memorias_semana:
        semana_txt += "\nMemorias extraidas da semana (banco de memoria):\n"
        for m in memorias_semana:
            semana_txt += f"  - {m}\n"

    interacoes_db = get_recent_interactions(days=7)
    if interacoes_db:
        semana_txt += "\nInteracoes da semana (Telegram/voz, banco de memoria):\n"
        for i in interacoes_db:
            semana_txt += f"  [{i['canal']}] {i['content']}\n"

    if not semana_txt.strip():
        semana_txt = "  (sem dados registrados esta semana)"

    prompt = f"""COMPILACAO SEMANAL — Analise a semana e proponha edicoes aos arquivos perenes.

{DIRETRIZES_RESUMO}

ESTADO ATUAL DOS ARQUIVOS PERENES:

--- guidelines.json (action_items) ---
{json.dumps(action_items, ensure_ascii=False, indent=2)}

--- guidelines.json (residents) ---
{json.dumps(residents, ensure_ascii=False, indent=2)}

AUTOMACOES ATUAIS DO AGENTE (permear_agent.yaml):
{autos_txt}

DADOS DA SEMANA (banco de memoria — memorias consolidadas + interacoes):
{semana_txt}

INSTRUCOES (relevancia > completude):

Analise os 7 dias e identifique APENAS as mudancas mais relevantes da semana.
Para insights: maximo 3 novas_sugestoes (apenas se realmente acionaveis) e novas_pendencias (apenas itens acionaveis da casa, nunca erros do framework).
Pendencias: SOMENTE itens da casa (temperatura, sensores, dispositivos, eletrodomesticos). NUNCA inclua erros do proprio framework PERMEAR/Nabu (compilacao_semanal, weekly_compile, byte offset, parse entities, etc).
Para proposed_automations: maximo 3 novas sugestoes. Verificar se ja existe na lista atual antes de adicionar.
Retornar APENAS JSON valido. Sem texto antes ou depois. Sem markdown fences. Se nao houver mudancas relevantes em uma categoria, retornar lista vazia [].

FORMATO JSON:
{{
"insights": {{"novos_padroes": [], "remover_padroes": [], "novas_pendencias": [], "remover_pendencias": [], "novas_sugestoes": []}},
"proposed_automations": [],
"remove_automations": []
}}"""

    print(prompt)


if __name__ == "__main__":
    main()
