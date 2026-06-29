"""ARAS — salience filter (Ascending Reticular Activating System).

PURE module: takes a candidate + user state, returns a score and decision.
Does NOT call the network, the LLM, HA, or the DB. Testable offline.
In-process port of scripts/lib/aras_filter.py (v8.9) — logic unchanged.

Inspiration: the ARAS filters stimuli by inhibition; only the salient emerges.
Four deterministic heuristics (sum -2 to 8) decide directly at the extremes.
The gray zone is flagged for the LLM to break the tie (caller's job).

The emit threshold is DYNAMIC and computed by the caller (heartbeat.py) —
this module never recalculates it; it only reads user_state['emit_threshold'].
"""

from datetime import datetime


def _novelty(candidate, user_state):
    """0-2. Compares the candidate's KEY against recent keys.
    Canonical key: 'type:entity_id' or 'type:content[:40]' — never raw text.
    """
    key = candidate.get("key", "")
    recent = user_state.get("recent_alerts", [])  # canonical keys

    if not recent:
        return 2

    # exact key match: same subject already alerted today
    if key and key in recent:
        return 0
    # same entity_id, different type = partially novel. Canonical-key
    # equality on the part after ':' — substring matching let light.sala
    # match light.sala_2 (different entity).
    entity = candidate.get("entity_id") or ""
    if entity and any(r.split(":", 1)[-1] == entity for r in recent):
        return 1

    return 2


def _anomaly(candidate, user_state):
    """0-1. Circadian heuristic on the EVENT's hour (when it actually happened),
    not the evaluation time. A 2am event stays anomalous even when first seen at
    the 08:30 cycle — using datetime.now() made anomaly permanently 0, since the
    Heartbeat only runs in the daytime window, so the spike could never fire.

    Pure: reads the hour from the candidate's own timestamp (LOCAL ISO
    'YYYY-MM-DDThh:mm:ss…'); falls back to the caller's evaluation hour only when
    the event carries no parseable timestamp.

    v9.2.2 — narrowed by habituation: an entity that REGULARLY acts at night is
    not anomalous at night for itself. The caller injects the set of habitually
    nocturnal entities (deterministic, from event_log); this only READS it, the
    filter stays pure. No history (a new entity) → not in the set → still
    anomalous (conservative; the unproven night event earns a look). A learned
    baseline replacing the whole circadian rule is a later reform — out of scope."""
    hour = _event_hour(candidate, user_state)
    if not 0 <= hour < 6:
        return 0
    entity = candidate.get("entity_id")
    if entity and entity in user_state.get("nocturnal_habitual", ()):
        return 0  # habituated — night is this entity's normal pattern
    return 1


def _event_hour(candidate, user_state) -> int:
    """Hour the event occurred, from candidate['timestamp'] (LOCAL ISO). Falls
    back to the evaluation hour (current_hour / now) when absent or malformed."""
    ts = candidate.get("timestamp") or ""
    if len(ts) >= 13 and ts[10] == "T" and ts[11:13].isdigit():
        return int(ts[11:13])
    return user_state.get("current_hour", datetime.now().hour)


def _priority(candidate, user_state):
    """0-2. Learned, read from entity_priorities (from monitored_entities.json)."""
    entity = candidate.get("entity_id")
    if not entity:
        return 0
    return int(user_state.get("entity_priorities", {}).get(entity, 0))


def _user_match(candidate, user_state):
    """-2 to 0. Penalty when the candidate matches a LEARNED restriction
    (v9.0.2: restriction memories, kind='behavior_rule', fed by the caller).

    Restrictions LOWER salience, never silence: -2 on the -2..8 scale still
    lets a strongly anomalous candidate (novelty+anomaly+priority) emerge.
    Entries may be dicts {content, entity_id} (memory restrictions — exact
    entity match wins) or plain strings (legacy word matching).
    """
    entity = candidate.get("entity_id") or ""
    content = (candidate.get("content") or "").lower()
    for restr in user_state.get("restrictions", []):
        if isinstance(restr, dict):
            r_entity = restr.get("entity_id")
            if r_entity and entity and r_entity == entity:
                return -2
            r = str(restr.get("content") or "").lower()
        else:
            r = str(restr).lower()
        # match if significant words of the restriction appear in the content
        sig_words = [w for w in r.split() if len(w) > 4]
        if sig_words and sum(1 for w in sig_words if w in content) >= max(1, len(sig_words) // 2):
            return -2
    return 0


def evaluate_salience(candidate, user_state):
    """
    candidate = {type, content, entity_id, timestamp}
    user_state = {restrictions, recent_alerts, entity_priorities, current_hour,
                  emit_threshold, suppress_threshold}
    Returns {salience, decision: emit|suppress|gray, rationale, scores}
    """
    nov = _novelty(candidate, user_state)
    ano = _anomaly(candidate, user_state)
    pri = _priority(candidate, user_state)
    usr = _user_match(candidate, user_state)

    score = nov + ano + pri + usr  # -2 to 8
    scores = {"novelty": nov, "anomaly": ano, "priority": pri, "user_match": usr}

    emit_threshold = user_state.get("emit_threshold", 5)
    suppress_threshold = user_state.get("suppress_threshold", 1)

    if score >= emit_threshold:
        decision = "emit"
    elif score <= suppress_threshold:
        decision = "suppress"
    else:
        decision = "gray"

    rationale = (f"score={score} (nov={nov} ano={ano} pri={pri} usr={usr}) "
                 f"thr={emit_threshold} -> {decision}")

    return {"salience": score, "decision": decision,
            "rationale": rationale, "scores": scores}
