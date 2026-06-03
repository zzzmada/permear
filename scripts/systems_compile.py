#!/usr/bin/env python3
"""
v7.1-G — Systems Consolidation result processor (weekly compile).
Receives the insights_json already parsed (no fence-strip).

The soul/users inputs were retired (auto-evolution abandoned in v8-S3/S4).
The caller still passes them as empty "{}" for arg-compatibility; they are
ignored. The full signature simplification happens with the cycles.yaml
caller (audit Phase 6).

Usage:
  systems_compile.py '<soul_json>' '<users_json>' '<insights_json>'
  (soul_json, users_json accepted but ignored)

insights_json = {"novos_padroes": [...], "remover_padroes": [...],
                 "novas_pendencias": [...], "remover_pendencias": [...],
                 "novas_sugestoes": [...]}
"""
import json, sys, os, re, shutil, unicodedata, yaml
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import (
    MEMORY_DIR, AGENT_YAML, LOG_DIR, DAYS, ENTITIES_PATH,
    ENGAGEMENT_MIN_ALERTS, ENGAGEMENT_UP_RATE, ENGAGEMENT_DOWN_RATE,
    GUIDELINES_PATH,
)
from lib.memory import load_json, save_json, locked_update
from lib.memory_db import get_emits_for_engagement

# ---------------------------------------------------------------------------
# Semantic helpers (deduplication of action_items by Jaccard similarity)
# ---------------------------------------------------------------------------
_STOPWORDS_PT = {
    "a", "o", "e", "de", "da", "do", "das", "dos", "em", "no", "na",
    "nos", "nas", "para", "por", "com", "sem", "que", "se", "ao", "aos",
    "as", "os", "um", "uma", "uns", "umas", "ou", "mas", "como", "quando",
    "muito", "muita", "muitos", "muitas", "ja", "ainda", "tambem", "so",
    "apenas", "ha", "tem", "tinha", "esta", "estao", "ser", "sera",
    "foi", "sao", "porque", "pois"
}


def _normalize_text(text):
    if not text:
        return []
    t = unicodedata.normalize("NFD", text.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z\s]", " ", t)
    return [w for w in t.split() if w and w not in _STOPWORDS_PT and len(w) > 2]


def _jaccard(text1, text2, threshold=0.7):
    t1, t2 = set(_normalize_text(text1)), set(_normalize_text(text2))
    if not t1 or not t2:
        return False
    union = len(t1 | t2)
    return union > 0 and (len(t1 & t2) / union) >= threshold


def is_duplicate_in_list(item, lista, threshold=0.7):
    return any(_jaccard(item, ex, threshold) for ex in lista)


META_KEYWORDS = [
    "weekly_compile", "compilacao_semanal", "byte offset",
    "cant parse entities", "parse entities", "compile.py",
    "weekly_compile_error", "process_log_event"
]


def is_meta_pendency(text):
    if not text:
        return False
    return any(kw in text.lower() for kw in META_KEYWORDS)


def count_agent_automations():
    if not os.path.exists(AGENT_YAML):
        return 0
    try:
        data = yaml.safe_load(open(AGENT_YAML))
        return len(data) if isinstance(data, list) else 0
    except Exception:
        return 0


def backup_file(path):
    if os.path.exists(path):
        shutil.copy2(path, path + f".bak.{datetime.now().strftime('%Y%m%d')}")


# ---------------------------------------------------------------------------
# Apply functions
# ---------------------------------------------------------------------------

def apply_insights_v2(current, changes):
    # v8-S1: current is now guidelines dict; data lives in action_items
    # novos_padroes/remover_padroes are ignored (patterns live in SQLite DB now)
    action = current.setdefault("action_items", {})
    counts = {
        "new_patterns": 0, "removed_patterns": 0,
        "pending_added": 0, "pending_removed": 0,
        "new_suggestions_list": []
    }

    existing_pend = action.get("pending", [])
    for p in changes.get("novas_pendencias", []):
        if is_meta_pendency(p) or is_duplicate_in_list(p, existing_pend):
            continue
        existing_pend.append(p)
        counts["pending_added"] += 1
    rem_pend = [p for p in changes.get("remover_pendencias", []) if p in existing_pend]
    for p in rem_pend:
        existing_pend.remove(p)
    counts["pending_removed"] = len(rem_pend)
    action["pending"] = existing_pend[:20]

    existing_sug = action.get("suggestions", [])
    for s in changes.get("novas_sugestoes", []):
        if s and not is_duplicate_in_list(s, existing_sug):
            existing_sug.append(s)
            counts["new_suggestions_list"].append(s)
    action["suggestions"] = existing_sug[:10]

    return current, counts


# ---------------------------------------------------------------------------
# v7.7-B — Engagement-based priority learning
# ---------------------------------------------------------------------------

def aggregate_engagement():
    """
    SD23-A — Reads source='heartbeat' from the DB (last 7d) instead of daily JSONs.
    Counts alerts and reactions per canonical key. Returns {key: {"alerts": N, "reacted": M}}.
    """
    stats = {}
    for row in get_emits_for_engagement(days=7):
        key = row["key"]
        meta = json.loads(row["metadata"]) if row.get("metadata") else {}
        stats.setdefault(key, {"alerts": 0, "reacted": 0})
        stats[key]["alerts"] += 1
        if meta.get("reacted"):
            stats[key]["reacted"] += 1
    return stats


def adjust_priorities_by_engagement():
    """
    v7.7-B — Adjusts entity priority based on the week's engagement.
    - priority_source 'user' (card) is NOT touched.
    - moves at most 1 level per run.
    Returns the list of changes for the report.
    """
    engagement = aggregate_engagement()
    if not engagement:
        return []

    changes = []
    with locked_update(ENTITIES_PATH, default={"entities": []}) as data:
        for e in data.get("entities", []):
            eid = e.get("entity_id")
            if not eid:
                continue
            # priority_source 'user' (set via card) is untouchable
            if e.get("priority_source") == "user":
                continue

            # aggregate all canonical keys pointing to this entity
            alerts = reacted = 0
            for key, st in engagement.items():
                if key.endswith(f":{eid}"):
                    alerts += st["alerts"]
                    reacted += st["reacted"]

            if alerts < ENGAGEMENT_MIN_ALERTS:
                continue

            rate = reacted / alerts
            cur = int(e.get("priority", 0))
            new = cur

            if rate >= ENGAGEMENT_UP_RATE and cur < 2:
                new = cur + 1
            elif rate <= ENGAGEMENT_DOWN_RATE and cur > 0:
                new = cur - 1

            if new != cur:
                e["priority"] = new
                e["priority_source"] = "learned"
                changes.append({
                    "entity": eid,
                    "from": cur,
                    "to": new,
                    "rate": round(rate, 2),
                    "alerts": alerts,
                })

    return changes


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
# NOTE: format_summary output is sent to Telegram (user-facing) — strings stay
# PT (i18n). Only code/comments are in English.

def format_summary(applied, agent_autos_count):
    lines = ["Resumo da semana:"]

    np_, rp = applied.get("new_patterns", 0), applied.get("removed_patterns", 0)
    if np_ or rp:
        lines.append(f"- Padroes: +{np_} -{rp}")

    ns = applied.get("new_suggestions_list", [])
    if ns:
        sample = ns[0][:80] if ns[0] else ""
        lines.append(f"- Sugestoes novas: {len(ns)} ({sample}{'...' if len(ns) > 1 else ''})")

    pa, pr = applied.get("pending_added", 0), applied.get("pending_removed", 0)
    if pa or pr:
        lines.append(f"- Pendencias: +{pa} -{pr}")

    # v7.7-B — priorities adjusted by engagement
    prio_changes = applied.get("priority_changes", [])
    if prio_changes:
        lines.append(f"- Prioridades ajustadas por engajamento: {len(prio_changes)}")
        for c in prio_changes:
            pct = int(c["rate"] * 100)
            lines.append(f"  - {c['entity']}: {c['from']}->{c['to']} (reagiu {pct}%, {c['alerts']} alertas)")
    else:
        lines.append("- Prioridades: nenhum ajuste.")

    if len(lines) == 2 and lines[-1] == "- Prioridades: nenhum ajuste.":
        lines.insert(1, "- Nenhuma mudanca relevante esta semana.")

    lines.append(f"- Automacoes do agente: {agent_autos_count} ativas")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_arg(arg, name):
    """Parse a JSON arg; return None if empty/invalid (graceful failure)."""
    if not arg or arg.strip() in ("", "{}", "[]", "null"):
        return None
    try:
        return json.loads(arg.strip())
    except (ValueError, json.JSONDecodeError) as e:
        print(f"WARNING: {name} invalid ({e}) — skipping this block.", file=sys.stderr)
        return None


def main():
    # argv[1]=soul, argv[2]=users are retired (accepted for caller arg-compat,
    # ignored); argv[3]=insights is the only live input. Full signature
    # simplification is coordinated with the cycles.yaml caller (audit Phase 6).
    if len(sys.argv) < 4:
        print("Usage: systems_compile.py '<soul_json>' '<users_json>' '<insights_json>'")
        sys.exit(1)

    insights_arg = sys.argv[3]
    insights_changes = parse_arg(insights_arg, "insights_json")

    guidelines_path = GUIDELINES_PATH

    backup_file(guidelines_path)

    applied = {
        "new_patterns": 0, "removed_patterns": 0,
        "new_suggestions_list": [],
        "pending_added": 0, "pending_removed": 0,
    }

    # Guidelines action_items (v8-S1: was insights.json)
    if insights_changes and isinstance(insights_changes, dict):
        with locked_update(guidelines_path, default={"action_items": {"suggestions": [], "pending": []}}) as guidelines:
            guidelines, ins_counts = apply_insights_v2(guidelines, insights_changes)
        applied["new_patterns"] = ins_counts["new_patterns"]
        applied["removed_patterns"] = ins_counts["removed_patterns"]
        applied["pending_added"] = ins_counts["pending_added"]
        applied["pending_removed"] = ins_counts["pending_removed"]
        applied["new_suggestions_list"] = ins_counts["new_suggestions_list"]

    # v7.7-B — ajuste de priority por engajamento da semana
    applied["priority_changes"] = adjust_priorities_by_engagement()

    print(format_summary(applied, count_agent_automations()))


if __name__ == "__main__":
    main()
