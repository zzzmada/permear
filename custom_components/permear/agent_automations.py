"""Standing notification rules, in-process (v9.17).

A rule is something the resident asked to be told: a trigger, an optional
condition and a message. Not an HA automation: a YAML file only works where
configuration.yaml happens to include it, and a HACS install must not depend on
that. The rules live in the integration's own data, are evaluated by the
Heartbeat module and only ever speak; nothing here touches a device.

Nothing is created without the resident's yes. The message is assembled in code
at delivery, with no LLM on that path. User-facing strings are PT.
"""

from __future__ import annotations

import json
import logging
import re
import uuid

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    RULE_ALIAS_MAX_BYTES,
    RULE_CONDITION_MARKERS,
    CONDITION_MAX_SECONDS,
    CONDITION_Q_COMPANION,
    CONDITION_Q_DURATION,
    CONDITION_Q_PRESENCE,
    CONDITION_WHEN_IGNORED,
    CONDITION_WHEN_MATTERS,
    MAX_AGENT_AUTOMATIONS,
    PRESENCE_RECENT_MINUTES,
    SIGNAL_RULES_CHANGED,
    SILENT_STATES,
    STANDING_RULES_RELATIVE_PATH,
)
from .storage import load_json, locked_json_update

_LOGGER = logging.getLogger(__name__)

# The only template a message may carry: the state of an entity. The text comes
# from an LLM, so anything else in {{ }} or {% %} is refused.
_MESSAGE_STATE_RE = re.compile(r"\{\{\s*states\(\s*'([\w.]+)'\s*\)\s*\}\}")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?$")


# ---------------------------------------------------------------------------
# Spec building — raw ai_task fields → a rule (pure)
# ---------------------------------------------------------------------------

def build_spec(raw: dict, consented_text: str = "") -> tuple[dict | None, str]:
    """{alias, trigger_type, trigger_config, action_message, condition_*}
    → rule. Returns (rule, "") or (None, PT reason)."""
    alias = str(raw.get("alias", "")).strip()
    if not alias:
        return None, "alias vazio"
    if len(alias.encode("utf-8")) > RULE_ALIAS_MAX_BYTES:
        return None, (f"apelido excede {RULE_ALIAS_MAX_BYTES} bytes; "
                      "acentos e emojis ocupam mais espaco")

    trigger = _build_trigger(raw.get("trigger_type"), raw.get("trigger_config"))
    if not trigger:
        return None, "gatilho nao suportado"

    message = str(raw.get("action_message", "")).strip()
    if not message:
        return None, "aviso sem mensagem"
    rest = _MESSAGE_STATE_RE.sub("", message)
    if "{{" in rest or "{%" in rest:
        return None, "mensagem com modelo nao permitido"

    # A condition the rule cannot carry is a refusal, never a silent drop: the
    # resident said yes to "at 18h if someone is home", not to "at 18h".
    condition = _build_condition(raw.get("condition_config"), trigger)
    if condition is None:
        return None, "condicao nao suportada"
    expresses_condition = any(
        re.search(r"(?<!\w)" + re.escape(marker) + r"(?!\w)", consented_text.casefold())
        for marker in RULE_CONDITION_MARKERS
    )
    if not condition and expresses_condition:
        return None, "a condicao aceita nao foi preservada"
    if not condition and str(raw.get("condition_text") or "").strip():
        return None, "condicao nao suportada"

    return {
        "id": f"aviso_{uuid.uuid4().hex[:8]}",
        "alias": alias,
        "trigger": trigger,
        "condition": condition,
        "message": message,
    }, ""


def _build_trigger(trigger_type, config_raw) -> dict | None:
    """{'at': 'HH:MM:SS'} or {'entity_id': x, 'to': state}."""
    cfg = _as_dict(config_raw)
    if not cfg:
        return None
    if trigger_type == "time" and _TIME_RE.match(str(cfg.get("at", ""))):
        return {"at": str(cfg["at"])}
    if trigger_type == "state" and cfg.get("entity_id") and cfg.get("to"):
        return {"entity_id": str(cfg["entity_id"]), "to": str(cfg["to"])}
    return None


def _build_condition(config_raw, trigger: dict) -> dict | None:
    """{} when none was given, a condition of the closed v9.13 schema, or None
    when one was given and does not fit it."""
    if config_raw is None or config_raw == {} or (
        isinstance(config_raw, str)
        and config_raw.strip().lower() in ("", "null", "none", "{}", "[]")
    ):
        return {}
    cfg = _as_dict(config_raw)
    if not cfg:
        return None
    when = CONDITION_WHEN_MATTERS
    if cfg.get("condition") == "not":
        nested = cfg.get("conditions")
        if not isinstance(nested, list) or len(nested) != 1:
            return None
        cfg, when = nested[0], CONDITION_WHEN_IGNORED
        if not isinstance(cfg, dict):
            return None
    kind = cfg.get("condition")
    if kind == "state" and cfg.get("entity_id") and "state" in cfg:
        return {"q": CONDITION_Q_COMPANION, "when": when,
                "entity_id": str(cfg["entity_id"]), "state": str(cfg["state"])}
    if kind == CONDITION_Q_PRESENCE:
        return {"q": CONDITION_Q_PRESENCE, "when": when,
                "minutes": PRESENCE_RECENT_MINUTES}
    # A state's duration can only be waited for, and only from a state trigger:
    # "held at most N" has no moment at which it could fire.
    if (kind == CONDITION_Q_DURATION and when == CONDITION_WHEN_MATTERS
            and "entity_id" in trigger):
        seconds = cfg.get("min_seconds")
        if isinstance(seconds, int) and 0 < seconds <= CONDITION_MAX_SECONDS:
            return {"q": CONDITION_Q_DURATION, "when": when,
                    "min_seconds": seconds}
    return None


def _as_dict(raw) -> dict | None:
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(raw) if isinstance(raw, str) else None
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def render_message(rule: dict, state_of) -> str | None:
    """The message with its entity states filled in, in code. None when one of
    them cannot be read now: a broken sentence is not a message."""
    missing = False

    def _state(match) -> str:
        nonlocal missing
        value = state_of(match.group(1))
        if value is None or value in SILENT_STATES:
            missing = True
            return ""
        return value

    text = _MESSAGE_STATE_RE.sub(_state, rule.get("message", ""))
    return None if missing else " ".join(text.split())


# ---------------------------------------------------------------------------
# PT summaries (cards)
# ---------------------------------------------------------------------------

def _entity_pt(eid: str) -> str:
    return eid.split(".")[1].replace("_", " ") if "." in eid else eid


def describe_when(rule: dict) -> str:
    trigger = rule.get("trigger") or {}
    if "at" in trigger:
        return f"Todo dia as {trigger['at']}"
    return (f"{_entity_pt(trigger.get('entity_id', '?')).capitalize()} "
            f"muda para {trigger.get('to', '?')}")


def describe_condition(rule: dict) -> str:
    condition = rule.get("condition") or {}
    negated = condition.get("when") == CONDITION_WHEN_IGNORED
    q = condition.get("q")
    if q == CONDITION_Q_COMPANION:
        relation = "nao esta" if negated else "esta"
        return (f"se {_entity_pt(condition['entity_id'])} {relation} em "
                f"{condition['state']}")
    if q == CONDITION_Q_PRESENCE:
        return "se houver alguem em casa" if negated else "se nao houver ninguem em casa"
    if q == CONDITION_Q_DURATION:
        return f"depois de {condition['min_seconds']}s nesse estado"
    return ""


def describe_trigger(rule: dict) -> str:
    condition = describe_condition(rule)
    return f"{describe_when(rule)}, {condition}" if condition else describe_when(rule)


def describe_action(rule: dict) -> str:
    return f"Avisar: {rule.get('message', '')}"


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

class AgentAutomations:
    """Read/create/remove the standing rules."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._path = hass.config.path(STANDING_RULES_RELATIVE_PATH)

    async def async_list(self) -> dict:
        rules = await self._hass.async_add_executor_job(self._load)
        items = [
            {"id": r.get("id", ""), "alias": r.get("alias", "sem nome"),
             "trigger_summary": describe_trigger(r)}
            for r in rules
        ]
        return {"count": len(items), "automations": items}

    async def async_list_text(self) -> str:
        """PT text for the LIST_AUTOS agent token."""
        rules = await self._hass.async_add_executor_job(self._load)
        if not rules:
            return "Nenhum aviso criado ainda."
        lines = [f"Avisos ativos ({len(rules)}):"]
        lines += [f"{i}. {r.get('alias', '?')} ({describe_trigger(r)})"
                  for i, r in enumerate(rules, 1)]
        return "\n".join(lines)

    def _load(self) -> list:
        rules = load_json(self._path, [])
        return rules if isinstance(rules, list) else []

    async def async_create(self, rule: dict) -> str:
        """Validate + persist. Returns the PT result message."""
        alias = str(rule.get("alias", "")).strip()
        if not alias:
            return "Erro: o aviso precisa de um nome."
        for ent_id in self._referenced_entities(rule):
            if self._hass.states.get(ent_id) is None:
                return f"Erro: a entidade {ent_id} nao existe no Home Assistant."
        error = await self._hass.async_add_executor_job(self._append, rule)
        if error:
            return error
        async_dispatcher_send(self._hass, SIGNAL_RULES_CHANGED)
        return f"Aviso criado: '{alias}'. Ativo a partir de agora."

    @staticmethod
    def _referenced_entities(rule: dict):
        for part in (rule.get("trigger") or {}, rule.get("condition") or {}):
            if part.get("entity_id"):
                yield part["entity_id"]
        yield from _MESSAGE_STATE_RE.findall(rule.get("message", ""))

    def _append(self, rule: dict) -> str:
        with locked_json_update(self._path, []) as rules:
            if len(rules) >= MAX_AGENT_AUTOMATIONS:
                return (f"Limite de {MAX_AGENT_AUTOMATIONS} avisos atingido. "
                        "Remova um antes de criar outro.")
            alias_lower = rule["alias"].lower()
            if any(str(r.get("alias", "")).lower() == alias_lower for r in rules):
                return f"Ja existe um aviso chamado '{rule['alias']}'."
            rules.append(rule)
        return ""

    async def async_remove(self, identifier: str) -> str:
        result = await self._hass.async_add_executor_job(self._remove, identifier)
        if result.startswith("Aviso removido"):
            async_dispatcher_send(self._hass, SIGNAL_RULES_CHANGED)
        return result

    def _remove(self, identifier: str) -> str:
        ident = identifier.strip().lower()
        with locked_json_update(self._path, []) as rules:
            idx = next(
                (i for i, r in enumerate(rules)
                 if ident in (str(r.get("id", "")).lower(),
                              str(r.get("alias", "")).lower())),
                None,
            )
            if idx is None:
                return f"Nenhum aviso encontrado com o nome '{identifier}'."
            removed = rules.pop(idx)
        return f"Aviso removido: '{removed.get('alias', identifier)}'."
