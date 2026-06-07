#!/usr/bin/env python3
"""
v7.1-F — Transforma spec intermediário em HA automation spec completo.

Lê de PENDING_SPEC_PATH e escreve de volta no formato HA canônico.
Sem argumentos — lê e sobrescreve o arquivo.

Suporta três formatos de entrada:
  1. Raw fields (de ai_task via JSON): tem chave "trigger_type", JSON válido
  2. Raw fields (de ai_task via YAML-style): HA renderiza MappingProxy como YAML
     Ex: {alias: Ligar AC, trigger_type: time, trigger_config: {...}}
  3. Spec HA direto (de conversation.process legado): tem "trigger" como lista
"""
import sys
import os
import json
import uuid
import ast
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.memory import save_json
from permear_config import PENDING_SPEC_PATH


def parse_file_content(raw):
    """Tenta JSON primeiro; fallback para YAML-style (gerado pelo HA para MappingProxy)."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    try:
        import yaml
        return yaml.safe_load(raw)
    except Exception:
        return None


def build_trigger_from_fields(trigger_type, trigger_config_raw):
    """Aceita trigger_config como dict (YAML-parsed) ou string (JSON ou Python repr)."""
    if isinstance(trigger_config_raw, dict):
        cfg = trigger_config_raw
    elif isinstance(trigger_config_raw, str):
        config_str = trigger_config_raw.strip()
        if not config_str or config_str.lower() in ("null", "none", "{}", ""):
            return None
        try:
            cfg = json.loads(config_str)
        except json.JSONDecodeError:
            try:
                cfg = ast.literal_eval(config_str)
            except (ValueError, SyntaxError):
                return None
    else:
        return None

    if not isinstance(cfg, dict):
        return None
    if "platform" not in cfg:
        cfg["platform"] = trigger_type
    return [cfg]


def build_action_from_fields(service, entity_id):
    if not service or not entity_id:
        return None
    return [{"service": service, "target": {"entity_id": entity_id}}]


def main():
    if not os.path.exists(PENDING_SPEC_PATH):
        print("ERROR: pending_auto_spec.json nao encontrado")
        sys.exit(1)

    with open(PENDING_SPEC_PATH, "r") as f:
        raw = f.read().strip()

    if not raw:
        print("ERROR: pending_auto_spec.json vazio")
        sys.exit(1)

    data = parse_file_content(raw)
    if data is None or not isinstance(data, dict):
        print("ERROR: formato invalido em pending_auto_spec.json (nem JSON nem YAML)")
        sys.exit(1)

    # Formato 1 e 2: raw fields de ai_task.generate_data (JSON ou YAML-style)
    if "trigger_type" in data:
        alias = str(data.get("alias", "")).strip()
        trigger_type = str(data.get("trigger_type", "time"))
        trigger_config_raw = data.get("trigger_config", "")
        action_service = str(data.get("action_service", ""))
        action_entity = str(data.get("action_entity", ""))

        if not alias:
            print("ERROR: alias vazio nos campos raw")
            sys.exit(1)

        trigger = build_trigger_from_fields(trigger_type, trigger_config_raw)
        if not trigger:
            tc_repr = str(trigger_config_raw)[:80]
            print(f"ERROR: trigger invalido. tipo='{trigger_type}' config='{tc_repr}'")
            sys.exit(1)

        action = build_action_from_fields(action_service, action_entity)
        if not action:
            print(f"ERROR: action invalida. service='{action_service}' entity='{action_entity}'")
            sys.exit(1)

        spec = {
            "id": f"agent_auto_{uuid.uuid4().hex[:8]}",
            "alias": alias,
            "trigger": trigger,
            "action": action,
            "mode": "single",
            "initial_state": "on",
        }
        if data.get("_condition_note"):
            spec["_condition_note"] = str(data["_condition_note"])

    # Formato 3: spec HA direto (de conversation.process legado)
    elif isinstance(data.get("trigger"), list):
        spec = data
        if not spec.get("id"):
            spec["id"] = f"agent_auto_{uuid.uuid4().hex[:8]}"
        spec.setdefault("mode", "single")
        spec.setdefault("initial_state", "on")

    else:
        print("ERROR: formato desconhecido (sem trigger_type nem trigger como lista)")
        sys.exit(1)

    save_json(PENDING_SPEC_PATH, spec)
    print(f"Spec construido: '{spec.get('alias', '?')}' (id={spec.get('id', '?')})")


if __name__ == "__main__":
    main()
