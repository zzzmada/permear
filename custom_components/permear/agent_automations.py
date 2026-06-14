"""CRUD for agent-created automations, in-process (v9.0-final).

Replaces the shell scripts manage_agent_automations.py +
build_automation_spec.py + write_pending_spec.py. Same target file:
/config/automations/permear_agent.yaml (loaded by HA's automation include).

What changed with the in-process port:
- entity validation via hass.states (no REST, no token);
- automation reload via hass.services ("automation"/"reload");
- the Supervisor pre-reload config check was dropped — the written YAML is
  re-parsed before reload and rolled back if invalid (the stronger guard);
- the pending spec lives in the Telegram handler's memory, not in
  pending_auto_spec.json / input_text (no shell state).

The agent CREATES nothing on its own — every write here is user-confirmed
through the Telegram cards. User-facing strings are PT without underscores
(rule #19). File I/O in the executor.
"""

from __future__ import annotations

import ast
import json
import logging
import time
import uuid

from homeassistant.core import HomeAssistant
from homeassistant.util.yaml import dump as yaml_dump
from homeassistant.util.yaml import load_yaml, parse_yaml

from .const import (
    AGENT_ACTION_DOMAINS,
    AGENT_AUTOMATIONS_RELATIVE_PATH,
    MAX_AGENT_AUTOMATIONS,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Spec building — raw ai_task fields → canonical HA automation spec
# (ports build_automation_spec.py; pure)
# ---------------------------------------------------------------------------

def build_spec(raw: dict) -> tuple[dict | None, str]:
    """{alias, trigger_type, trigger_config, action_service, action_entity}
    → canonical spec. Returns (spec, "") or (None, PT error)."""
    alias = str(raw.get("alias", "")).strip()
    if not alias:
        return None, "alias vazio"

    trigger_type = str(raw.get("trigger_type", "time"))
    trigger = _build_trigger(trigger_type, raw.get("trigger_config", ""))
    if not trigger:
        tc_repr = str(raw.get("trigger_config", ""))[:80]
        return None, f"gatilho invalido (tipo '{trigger_type}', config '{tc_repr}')"

    action_service = str(raw.get("action_service", "")).strip()
    action_entity = str(raw.get("action_entity", "")).strip()
    if not action_service or not action_entity:
        return None, (f"acao invalida (service '{action_service}', "
                      f"entidade '{action_entity}')")
    if action_service.partition(".")[0] not in AGENT_ACTION_DOMAINS:
        return None, f"servico nao permitido ('{action_service}')"

    return {
        "id": f"agent_auto_{uuid.uuid4().hex[:8]}",
        "alias": alias,
        "trigger": trigger,
        "action": [{"service": action_service,
                    "target": {"entity_id": action_entity}}],
        "mode": "single",
        "initial_state": "on",
    }, ""


def _build_trigger(trigger_type: str, config_raw) -> list | None:
    if isinstance(config_raw, dict):
        cfg = config_raw
    elif isinstance(config_raw, str):
        config_str = config_raw.strip()
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
    cfg.setdefault("platform", trigger_type)
    return [cfg]


# ---------------------------------------------------------------------------
# PT summaries (cards) — port the telegram.yaml Jinja + script summaries
# ---------------------------------------------------------------------------

def _entity_pt(eid: str) -> str:
    return eid.split(".")[1].replace("_", " ") if "." in eid else eid


def describe_trigger(spec: dict) -> str:
    triggers = spec.get("trigger") or []
    t = triggers[0] if triggers else {}
    platform = t.get("platform", "")
    if platform == "time":
        return f"Todo dia as {t.get('at', '?')}"
    if platform == "state":
        nome = _entity_pt(t.get("entity_id", "?"))
        return f"{nome.capitalize()} muda para {t.get('to', 'novo estado')}"
    if platform == "numeric_state":
        nome = _entity_pt(t.get("entity_id", "?"))
        if t.get("above") is not None:
            return f"{nome.capitalize()} acima de {t['above']}"
        if t.get("below") is not None:
            return f"{nome.capitalize()} abaixo de {t['below']}"
        return f"{nome.capitalize()} valor limite"
    if platform == "time_pattern":
        if t.get("hours"):
            return f"A cada {t['hours']} hora(s)"
        if t.get("minutes"):
            return f"A cada {t['minutes']} minuto(s)"
        return "Padrao de tempo recorrente"
    if platform == "sun":
        return ("Ao nascer do sol" if t.get("event") == "sunrise"
                else "Ao por do sol")
    if platform == "homeassistant":
        return "Quando o Home Assistant inicia"
    return "Gatilho configurado"


_ACTION_VERBS_PT = {
    ("light", "turn_on"): "Ligar luz",
    ("light", "turn_off"): "Desligar luz",
    ("climate", "turn_on"): "Ligar ar condicionado",
    ("climate", "turn_off"): "Desligar ar condicionado",
    ("climate", "set_temperature"): "Ajustar temperatura",
    ("media_player", "turn_on"): "Ligar midia",
    ("media_player", "turn_off"): "Desligar midia",
}


def describe_action(spec: dict) -> str:
    actions = spec.get("action") or []
    a = actions[0] if actions else {}
    svc = a.get("service", a.get("action", ""))
    domain, _, cmd = svc.partition(".")
    eid = (a.get("target") or {}).get("entity_id", a.get("entity_id", ""))
    nome = _entity_pt(eid) if eid else ""

    label = _ACTION_VERBS_PT.get((domain, cmd))
    if label:
        return f"{label} {nome}".strip()
    if domain == "switch":
        verb = "Ligar" if cmd == "turn_on" else "Desligar"
        return f"{verb} {nome or 'dispositivo'}"
    if domain == "script":
        return f"Executar script {nome}".strip()
    if cmd == "turn_on":
        return f"Ligar {nome or svc}"
    if cmd == "turn_off":
        return f"Desligar {nome or svc}"
    return svc or "acao configurada"


def _summarize_trigger_short(triggers) -> str:
    """Short PT trigger summary for the list card (ports _summarize_trigger)."""
    if not triggers:
        return "sem gatilho"
    if not isinstance(triggers, list):
        triggers = [triggers]
    t = triggers[0]
    platform = t.get("platform", "?")
    if platform == "time":
        return f"todo dia as {t.get('at', '?')}"
    if platform == "state":
        to = t.get("to")
        entity = t.get("entity_id", "?")
        return f"{entity} mudar para {to}" if to else f"{entity} mudar de estado"
    if platform == "numeric_state":
        entity = t.get("entity_id", "?")
        if t.get("above") is not None:
            return f"{entity} acima de {t['above']}"
        if t.get("below") is not None:
            return f"{entity} abaixo de {t['below']}"
        return f"{entity} (valor numerico)"
    if platform == "time_pattern":
        return "padrao de tempo recorrente"
    return f"gatilho {platform}"


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

class AgentAutomations:
    """Read/create/remove automations in permear_agent.yaml."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._path = hass.config.path(AGENT_AUTOMATIONS_RELATIVE_PATH)

    # -- reads ----------------------------------------------------------

    async def async_list(self) -> dict:
        autos = await self._hass.async_add_executor_job(self._load)
        items = [
            {
                "id": a.get("id", ""),
                "alias": a.get("alias", "sem nome"),
                "enabled": a.get("initial_state", "on") == "on",
                "trigger_summary": _summarize_trigger_short(a.get("trigger", [])),
            }
            for a in autos
        ]
        return {"count": len(items), "automations": items}

    async def async_list_text(self) -> str:
        """PT text for the LIST_AUTOS agent token."""
        autos = await self._hass.async_add_executor_job(self._load)
        if not autos:
            return "Nenhuma automacao criada ainda."
        lines = [f"Automacoes ativas ({len(autos)}):"]
        for i, a in enumerate(autos, 1):
            triggers = a.get("trigger") or []
            actions = a.get("action") or []
            lines.append(f"{i}. {a.get('alias', '?')} "
                         f"({len(triggers)} gatilho, {len(actions)} acao)")
        return "\n".join(lines)

    def _load(self) -> list:
        try:
            data = load_yaml(self._path)
        except (FileNotFoundError, OSError):
            return []
        except Exception as exc:  # noqa: BLE001 — corrupted file must not crash
            _LOGGER.warning("Cannot parse %s: %s", self._path, exc)
            return []
        return data if isinstance(data, list) else []

    # -- create ---------------------------------------------------------

    async def async_create(self, spec: dict) -> str:
        """Validate + append + reload. Returns the PT result message."""
        alias = str(spec.get("alias", "")).strip()
        if not alias:
            return "Erro: a automacao precisa de um nome."

        trigger = spec.get("trigger")
        if isinstance(trigger, dict):
            trigger = [trigger]
        if not trigger:
            return "Erro: a automacao precisa de um gatilho."
        action = spec.get("action")
        if isinstance(action, dict):
            action = [action]
        if not action:
            return "Erro: a automacao precisa de uma acao."
        for a in action:
            if "action" in a and "service" not in a:
                a["service"] = a.pop("action")

        # Action-domain allowlist — the spec text comes from an LLM; never
        # write homeassistant.*/shell_command.*/python_script.* automations
        for a in action:
            svc = str(a.get("service", ""))
            if svc.partition(".")[0] not in AGENT_ACTION_DOMAINS:
                return f"Erro: servico '{svc}' nao permitido em automacoes do agente."

        # Entity validation straight from the state machine (no REST)
        for ent_id in self._referenced_entities(trigger, action):
            if self._hass.states.get(ent_id) is None:
                return f"Erro: a entidade {ent_id} nao existe no Home Assistant."

        spec = {
            "alias": alias,
            "id": spec.get("id") or f"permear_agent_{int(time.time())}",
            "trigger": trigger,
            "condition": spec.get("condition", []),
            "action": action,
            "mode": spec.get("mode", "single"),
            "initial_state": spec.get("initial_state", "on"),
        }

        error = await self._hass.async_add_executor_job(self._append, spec)
        if error:
            return error

        reloaded = await self._reload()
        if reloaded:
            return f"Automacao criada: '{alias}'. Ativa imediatamente."
        return (f"Automacao criada: '{alias}'. O reload falhou — "
                "ativa no proximo reinicio do Home Assistant.")

    @staticmethod
    def _referenced_entities(trigger: list, action: list):
        for t in trigger:
            if isinstance(t, dict) and t.get("entity_id"):
                yield t["entity_id"]
        for a in action:
            if not isinstance(a, dict):
                continue
            if (a.get("data") or {}).get("entity_id"):
                yield a["data"]["entity_id"]
            if (a.get("target") or {}).get("entity_id"):
                yield a["target"]["entity_id"]

    def _append(self, spec: dict) -> str:
        """Executor: append + write + revalidate, rollback on bad YAML."""
        autos = self._load()
        if len(autos) >= MAX_AGENT_AUTOMATIONS:
            return (f"Limite de {MAX_AGENT_AUTOMATIONS} automacoes atingido. "
                    "Remova uma antes de criar outra.")
        alias_lower = spec["alias"].lower()
        for a in autos:
            if str(a.get("alias", "")).lower() == alias_lower:
                return f"Ja existe uma automacao chamada '{spec['alias']}'."
        autos.append(spec)
        if not self._write_validated(autos):
            autos.pop()
            self._write_validated(autos)
            return "Erro ao gravar a automacao (YAML invalido). Nada foi criado."
        return ""

    # -- remove ---------------------------------------------------------

    async def async_remove(self, identifier: str) -> str:
        result = await self._hass.async_add_executor_job(self._remove, identifier)
        if result.startswith("Automacao removida"):
            await self._reload()
        return result

    def _remove(self, identifier: str) -> str:
        autos = self._load()
        ident = identifier.strip().lower()
        idx = next(
            (i for i, a in enumerate(autos)
             if str(a.get("id", "")).lower() == ident
             or str(a.get("alias", "")).lower() == ident),
            None,
        )
        if idx is None:
            return f"Nenhuma automacao encontrada com o nome '{identifier}'."
        removed = autos.pop(idx)
        if not self._write_validated(autos):
            autos.insert(idx, removed)
            self._write_validated(autos)
            return "Erro ao gravar a remocao (YAML invalido). Automacao restaurada."
        return f"Automacao removida: '{removed.get('alias', identifier)}'."

    # -- shared ---------------------------------------------------------

    def _write_validated(self, autos: list) -> bool:
        """Validate, then write — invalid YAML never touches the file."""
        try:
            text = yaml_dump(autos)
            parse_yaml(text)
            with open(self._path, "w", encoding="utf-8") as fh:
                fh.write(text)
            return True
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("Agent automations YAML write failed: %s", exc)
            return False

    async def _reload(self) -> bool:
        try:
            await self._hass.services.async_call(
                "automation", "reload", {}, blocking=True
            )
            return True
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("automation.reload failed: %s", exc)
            return False
