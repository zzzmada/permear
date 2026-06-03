"""
v7.5 — ARAS: salience filter (Ascending Reticular Activating System).
PURE module: takes a candidate + user state, returns a score.
Does NOT call the network, the LLM, or HA. Testable offline.

Inspiration: the ARAS filters stimuli by inhibition; only the salient emerges.
Phase 1 (4 deterministic heuristics, sum -2 to 8) decides directly at the
extremes. The gray zone (2-5) is flagged for the LLM to break the tie (caller).
"""
from datetime import datetime


def _parse_ts(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def _novelty(candidate, user_state):
    """0-2. Compares the candidate's KEY against recent keys.
    v7.7-A: fixes the bug of comparing a raw token vs human text.
    Canonical key: 'type:entity_id' or 'type:content[:40]'.
    """
    key = candidate.get("key", "")
    recent = user_state.get("recent_alerts", [])  # v7.7-A: canonical keys

    if not recent:
        return 2

    # exact key match: same subject already alerted today
    if key and key in recent:
        return 0
    # same entity_id, different type = partially novel
    entity = candidate.get("entity_id") or ""
    if entity and any(entity in r for r in recent):
        return 1

    return 2


def _anomaly(candidate, user_state):
    """0-2. v7.5 simple: small hours (0-6h) = +1 for any entity.
    v7.7 will evolve into a per-entity temporal map (max 2)."""
    hour = user_state.get("current_hour", datetime.now().hour)
    if 0 <= hour < 6:
        return 1
    return 0


def _priority(candidate, user_state):
    """0-2. Learned, read from entity_priorities (from monitored_entities.json)."""
    entity = candidate.get("entity_id")
    if not entity:
        return 0
    return int(user_state.get("entity_priorities", {}).get(entity, 0))


def _user_match(candidate, user_state):
    """-2 to 0. Penalty if it matches a user restriction."""
    content = (candidate.get("content") or "").lower()
    for restr in user_state.get("restrictions", []):
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

    v7.9-C: emit_threshold is read from user_state (computed by the caller via
    compute_dynamic_threshold). Default=5 preserves the previous behavior.
    aras_filter stays PURE: no DB reads, no LLM calls.
    """
    nov = _novelty(candidate, user_state)
    ano = _anomaly(candidate, user_state)
    pri = _priority(candidate, user_state)
    usr = _user_match(candidate, user_state)

    score = nov + ano + pri + usr  # -2 to 8
    scores = {"novelty": nov, "anomaly": ano, "priority": pri, "user_match": usr}

    # v7.9-C: dynamic threshold via user_state; default=5 for safe rollback
    emit_threshold = user_state.get("emit_threshold", 5)
    # suppress_threshold fixed at 1 (only emit is dynamic for now)
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
