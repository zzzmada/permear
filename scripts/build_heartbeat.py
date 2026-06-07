#!/usr/bin/env python3
"""
Heartbeat core — builds the hourly attentional cycle's candidate set and
gray-zone prompt.
v5.0: reads monitored_entities.json via REST API, includes health summary.
v7.3-A: bulk fetch /api/states (1 call vs N sequential).
v7.5-B: ARAS filter — candidates classified, LLM only for the gray zone.
         Output: JSON {emits, gray_prompt, stats} instead of plain text.
v7.6:   scan_battery_signals + enriched gray prompt + circuit-breaker health.
"""
import json
import os
import sys
import yaml
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import *
from lib.memory import load_json, locked_update
from lib.agent import get_health_summary_for_prompt
from lib.aras_filter import evaluate_salience
from lib.memory_db import count_consolidated, get_today_emitted_keys, get_today_events


def load_token():
    try:
        with open(TOKEN_PATH, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


def fetch_all_states(token):
    """v7.3-A — Single bulk fetch instead of N sequential calls."""
    url = f"{HA_URL}/api/states"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=10) as resp:
            states = json.loads(resp.read().decode())
        return {s["entity_id"]: s for s in states if isinstance(s, dict)}
    except (URLError, json.JSONDecodeError) as e:
        print(f"WARNING: bulk fetch failed ({e})", file=sys.stderr)
        return {}


def format_entity_state(entity_id, states_dict):
    """Format single entity from pre-fetched dict."""
    s = states_dict.get(entity_id)
    if not s:
        return "unavailable"
    state = s.get("state", "unavailable")
    attrs = s.get("attributes", {})
    unit = attrs.get("unit_of_measurement", "")
    return f"{state}{' ' + unit if unit else ''}"


def load_agent_automations():
    if not os.path.exists(AGENT_YAML):
        return []
    try:
        with open(AGENT_YAML, 'r') as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, list) else []
    except (yaml.YAMLError, TypeError):
        return []


# =============================================================================
# v7.9-C — ARAS: dynamic threshold by memory maturity
# =============================================================================

def compute_dynamic_threshold(exposed_count):
    """
    Emit threshold relative to maturity. Pure computation (arithmetic).
    maturity = consolidated / exposed, saturating at ARAS_MATURITY_FULL_RATIO.
    threshold = MIN + maturity * (MAX - MIN).
    Edges: park < MIN_ENTITIES -> MIN (curious, no oscillation).
    """
    if not exposed_count or exposed_count < ARAS_MATURITY_MIN_ENTITIES:
        return ARAS_THRESHOLD_MIN
    consolidated = count_consolidated()
    ratio = consolidated / exposed_count
    maturity = min(ratio / ARAS_MATURITY_FULL_RATIO, 1.0)  # 0..1, saturado
    span = ARAS_THRESHOLD_MAX - ARAS_THRESHOLD_MIN
    return round(ARAS_THRESHOLD_MIN + maturity * span)


# =============================================================================
# v7.5-B — ARAS: candidate generation and user state
# =============================================================================

def _candidate_key(cand):
    """Stable canonical key: type:entity_id, or type:content[:40] if no entity."""
    eid = cand.get("entity_id")
    ctype = cand.get("type", "event")
    if eid:
        return f"{ctype}:{eid}"
    content = (cand.get("content") or "").lower().strip()
    return f"{ctype}:{content[:40]}"


def scan_battery_signals(states_dict, monitored_ids):
    """
    v7.6 — Scans battery entities below the threshold.
    Agnostic: by device_class 'battery' OR by name pattern.
    Only considers monitored entities (exposed by the user).
    """
    candidates = []
    now_iso = datetime.now().isoformat()
    for eid, s in states_dict.items():
        if eid not in monitored_ids:
            continue
        attrs = s.get("attributes", {})
        dc = attrs.get("device_class", "")
        is_battery = (dc in BATTERY_DEVICE_CLASSES or
                      any(p in eid for p in BATTERY_ENTITY_PATTERNS))
        if not is_battery:
            continue
        try:
            level = float(s.get("state"))
        except (ValueError, TypeError):
            continue
        if level < BATTERY_THRESHOLD:
            friendly = attrs.get("friendly_name", eid)
            candidates.append({
                "type": "battery_low",
                "content": f"Bateria baixa: {friendly} em {level:.0f}%",
                "entity_id": eid,
                "timestamp": now_iso,
            })
    return candidates


def scan_silent_entities(states_dict):
    """
    v7.6-C — Detects entities that transitioned available -> silent.
    Connectivity health: GLOBAL by design (Option A contract), not filtered by
    monitored_entities — an offline device matters regardless of exposure.
    Only generates a candidate on the TRANSITION (available -> silent), not every cycle.
    First cycle with no prior snapshot: creates a baseline with no candidates (correct).
    """
    now_iso = datetime.now().isoformat()
    candidates = []

    with locked_update(AVAILABILITY_PATH, {}) as snapshot:
        new_snapshot = {}
        for eid, s in states_dict.items():
            domain = eid.split(".")[0]
            if domain in SILENT_IGNORE_DOMAINS:
                continue
            cur_state = s.get("state", "")
            is_silent = cur_state in SILENT_STATES
            cur_label = "silent" if is_silent else "available"
            new_snapshot[eid] = {"last_state": cur_label, "since": now_iso}

            prev = snapshot.get(eid)
            if prev:
                if prev.get("last_state") == cur_label:
                    new_snapshot[eid]["since"] = prev.get("since", now_iso)
                # transition available -> silent: generate candidate
                if prev.get("last_state") == "available" and is_silent:
                    friendly = s.get("attributes", {}).get("friendly_name", eid)
                    candidates.append({
                        "type": "entity_silent",
                        "content": f"Dispositivo parou de responder: {friendly}",
                        "entity_id": eid,
                        "timestamp": now_iso,
                    })

        snapshot.clear()
        snapshot.update(new_snapshot)

    return candidates


_HUMANIZE_VERBS = frozenset({
    "ligou", "desligou", "chegou", "saiu", "abriu", "fechou",
    "aberta", "fechada", "mudou", "ativo", "inativo",
})


def _humanize_event(detalhe, entity_id, states_dict):
    """Convert a raw trigger ID to a human-readable PT string.
    Prefers friendly_name + verb suffix; falls back to prettified trigger ID.
    """
    if " " in detalhe:
        return detalhe  # already human-readable
    fname = ""
    if entity_id and states_dict:
        s = states_dict.get(entity_id, {})
        fname = s.get("attributes", {}).get("friendly_name", "")
    if fname:
        # Extract last segment as verb hint (e.g. "tv_sala_ligou" → "ligou")
        suffix = detalhe.rsplit("_", 1)[-1]
        if suffix in _HUMANIZE_VERBS:
            return f"{fname}: {suffix}"
        return fname
    return detalhe.replace("_", " ").capitalize()


def build_candidates(health_summary, monitored, states_dict=None):
    """
    Builds the candidate list from the current state.
    Each candidate: {type, content, entity_id, timestamp}
    v7.5-B: today's events + health errors.
    v7.6: battery below threshold + circuit-breaker health.
    v8.3: human-readable content for buffer events.
    """
    candidates = []
    now_iso = datetime.now().isoformat()

    # SD4: events from event_buffer (DB) instead of the daily JSON
    for ev in get_today_events():
        detalhe = ev.get("detalhe", "")
        if detalhe.startswith("erro:"):  # errors go through monitor, not ARAS (CLAUDE.md)
            continue
        entity_id = ev.get("entity_id")
        content = _humanize_event(detalhe, entity_id, states_dict)
        candidates.append({
            "type": "event",
            "content": content,
            "entity_id": entity_id,
            "timestamp": ev.get("ts", now_iso),
            "metadata": ev.get("metadata", "{}"),
        })

    if "SELF_ERRORS" in health_summary or "ERRORS" in health_summary:
        candidates.append({
            "type": "error",
            "content": health_summary,
            "entity_id": None,
            "timestamp": now_iso,
        })

    # v7.6 — circuit-breaker health (retries, fallbacks, final failures)
    health_circuit = get_health_summary_for_prompt()
    if health_circuit:
        candidates.append({
            "type": "health",
            "content": health_circuit,
            "entity_id": None,
            "timestamp": now_iso,
        })

    # v7.6 — battery/signal below threshold
    # Uses all entities in the file (not only monitor=True): battery sensors are
    # tracked but rarely exposed to the VA — monitor=False is incidental here.
    if states_dict is not None:
        all_file_ids = {e["entity_id"] for e in monitored.get("entities", [])}
        candidates.extend(scan_battery_signals(states_dict, all_file_ids))

    # v7.6-C — connectivity: entities that stopped responding (global by design)
    if states_dict is not None:
        candidates.extend(scan_silent_entities(states_dict))

    # v7.7-A: the canonical key unifies dedup and novelty tracking
    seen: set = set()
    deduped = []
    for c in candidates:
        c["key"] = _candidate_key(c)
        if c["key"] not in seen:
            seen.add(c["key"])
            deduped.append(c)
    return deduped


def build_user_state(users, monitored, daily):
    """Builds the user state consumed by the ARAS filter."""
    resident = users.get(PRIMARY_RESIDENT, {})

    # SD23-A: recent_alerts from the DB (source='heartbeat', today) — was interacoes[] in JSON
    recent_keys = get_today_emitted_keys()

    # v7.7-A: orphan priority — an entity with monitor:false must not have an active priority
    priorities = {}
    exposed = []
    for e in monitored.get("entities", []):
        if not e.get("monitor", True):
            continue
        eid = e.get("entity_id")
        if eid:
            priorities[eid] = int(e.get("priority", 0))
            exposed.append(eid)

    # v7.9-C: dynamic threshold — born curious (MIN=2), rises with maturity
    emit_threshold = compute_dynamic_threshold(len(exposed))

    return {
        "restrictions": resident.get("restrictions", []),
        "recent_alerts": recent_keys,
        "entity_priorities": priorities,
        "current_hour": datetime.now().hour,
        "emit_threshold": emit_threshold,   # v7.9-C: dynamic
        "suppress_threshold": 1,            # fixed for now
    }


def build_gray_prompt(grays, users, states_dict=None):
    """Prompt focused only on gray-zone candidates for the LLM to break the tie.
    NOTE: the returned prompt text stays PT — it shapes user-facing PT output and
    ends with the sentinel SILENCIO parsed by the cycle. Do not translate it."""
    itens_parts = []
    for c, r in grays:
        line = f"  - {c['content']} (saliencia {r['salience']})"
        eid = c.get("entity_id")
        if eid and states_dict:
            s = states_dict.get(eid)
            if s:
                attrs = s.get("attributes", {})
                dc = attrs.get("device_class", "") or eid.split(".")[0]
                unit = attrs.get("unit_of_measurement", "")
                state_val = s.get("state", "?")
                state_str = f"{state_val}{' '+unit if unit else ''}"
                last_upd = (s.get("last_updated") or "")[:16].replace("T", " ")
                line += (f"\n  [estado atual: {state_str} | tipo: {dc}"
                         f" | última atualização: {last_upd}]")
        itens_parts.append(line)
    itens = "\n".join(itens_parts)

    restricoes = users.get(PRIMARY_RESIDENT, {}).get("restrictions", [])
    restr_txt = "\n".join(f"  - {r}" for r in restricoes) or "  Nenhuma."

    return f"""Avalie quais destes eventos merecem avisar o morador AGORA.

EVENTOS A AVALIAR (zona cinzenta do filtro de saliencia):
{itens}

RESTRICOES (nunca avisar):
{restr_txt}

Para CADA evento, decida emitir ou silenciar. Responda so com os eventos que
merecem aviso, em mensagens curtas (max 2 frases cada). Se nenhum merece,
responda EXATAMENTE: SILENCIO."""


def main():
    hoje_idx = datetime.now().weekday()
    dia_nome = DAYS[hoje_idx]

    guidelines = load_json(GUIDELINES_PATH, {})
    users = guidelines.get("residents", {})
    monitored = load_json(ENTITIES_PATH, {"entities": []})

    health_summary = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "HEALTH: OK"

    token = load_token()
    states_dict = fetch_all_states(token) if token else {}

    # --- ARAS: generate candidates and classify ---
    # SD4: daily arg removed — build_candidates reads events from event_buffer (DB)
    candidates = build_candidates(health_summary, monitored, states_dict)
    user_state = build_user_state(users, monitored, {})

    emits = []
    grays = []
    suppressed = 0

    for cand in candidates:
        result = evaluate_salience(cand, user_state)
        if result["decision"] == "emit":
            emits.append((cand, result))
        elif result["decision"] == "gray":
            grays.append((cand, result))
        else:
            suppressed += 1

    output = {
        "emits": [{"content": c["content"], "key": c["key"], "metadata": c.get("metadata", "{}")} for c, r in emits],
        "gray_prompt": build_gray_prompt(grays, users, states_dict) if grays else "",
        "stats": {
            "total": len(candidates),
            "emit": len(emits),
            "gray": len(grays),
            "suppress": suppressed,
            "emit_threshold": user_state.get("emit_threshold", 5),  # v7.9-C
        },
    }
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
