#!/usr/bin/env python3
"""
v7.1-G — Weekly compilation with 3 structured inputs from ai_task.
v7.3-B.2 — migrated to locked_update (atomic per-file updates).

Receives soul_json, users_json, insights_json already parsed.

Usage:
  weekly_compile.py '<soul_json>' '<users_json>' '<insights_json>'
"""
import json, sys, os, re, shutil, unicodedata, yaml
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import MEMORY_DIR, AGENT_YAML, LOG_DIR, DAYS
from lib.memory import locked_update

# ---------------------------------------------------------------------------
# Semantic helpers (Jaccard dedup, meta-pendency filter)
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "of", "in", "on", "at", "to",
    "for", "with", "without", "by", "from", "as", "is", "are", "was", "were",
    "be", "been", "being", "has", "have", "had", "do", "does", "did",
    "this", "that", "these", "those", "it", "its", "they", "them",
    "i", "you", "he", "she", "we", "us", "him", "her", "his", "hers",
    "my", "your", "their", "our", "if", "then", "else", "when", "while"
}


def _normalize_text(text):
    if not text:
        return []
    t = unicodedata.normalize("NFD", text.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z\s]", " ", t)
    return [w for w in t.split() if w and w not in _STOPWORDS and len(w) > 2]


def _jaccard(text1, text2, threshold=0.7):
    t1, t2 = set(_normalize_text(text1)), set(_normalize_text(text2))
    if not t1 or not t2:
        return False
    union = len(t1 | t2)
    return union > 0 and (len(t1 & t2) / union) >= threshold


def is_duplicate_in_list(item, lst, threshold=0.7):
    return any(_jaccard(item, ex, threshold) for ex in lst)


META_KEYWORDS = [
    "weekly_compile", "byte offset",
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
# Apply functions (mutate state dict in-place)
# ---------------------------------------------------------------------------

def apply_soul(current, changes):
    """changes = {add: [...], remove: [...]}, applied to behavior_rules."""
    added = removed = 0
    rules = current.get("behavior_rules", [])
    for r in changes.get("add", []):
        r = str(r).strip()
        if r and r not in rules:
            rules.append(r)
            added += 1
    for r in changes.get("remove", []):
        r = str(r).strip()
        if r and r in rules:
            rules.remove(r)
            removed += 1
    current["behavior_rules"] = rules[:15]
    return added, removed


def apply_users(current, changes):
    """changes = {user_key: {add: [...], remove: [...]}}, applied to observed_patterns."""
    user_changes = []
    for user_key, user_edits in changes.items():
        if user_key not in current:
            continue
        field = "observed_patterns"
        lst = current[user_key].get(field, [])
        if not isinstance(lst, list):
            lst = []
        added = [p for p in user_edits.get("add", []) if str(p).strip() and str(p).strip() not in lst]
        for p in added:
            lst.append(str(p).strip())
        removed = [p for p in user_edits.get("remove", []) if str(p).strip() in lst]
        for p in removed:
            lst.remove(str(p).strip())
        current[user_key][field] = lst[-15:]
        if added or removed:
            user_changes.append(f"{user_key}: +{len(added)} -{len(removed)}")
    return "; ".join(user_changes)


def apply_insights(current, changes):
    max_patterns = 30
    counts = {
        "new_patterns": 0, "removed_patterns": 0,
        "pending_added": 0, "pending_removed": 0,
        "new_suggestions_list": []
    }

    existing_patterns = current.get("detected_patterns", [])
    new = [p for p in changes.get("new_patterns", [])
           if p and not is_duplicate_in_list(p, existing_patterns)]
    for p in new:
        existing_patterns.append(p)
    counts["new_patterns"] = len(new)
    current["detected_patterns"] = existing_patterns[-max_patterns:]

    removed = [p for p in changes.get("remove_patterns", []) if p in current.get("detected_patterns", [])]
    for p in removed:
        current["detected_patterns"].remove(p)
    counts["removed_patterns"] = len(removed)

    existing_pend = current.get("pending", [])
    for p in changes.get("new_pending", []):
        if is_meta_pendency(p) or is_duplicate_in_list(p, existing_pend):
            continue
        existing_pend.append(p)
        counts["pending_added"] += 1
    rem_pend = [p for p in changes.get("remove_pending", []) if p in existing_pend]
    for p in rem_pend:
        existing_pend.remove(p)
    counts["pending_removed"] = len(rem_pend)
    current["pending"] = existing_pend[:20]

    existing_sug = current.get("automation_suggestions", [])
    for s in changes.get("new_suggestions", []):
        if s and not is_duplicate_in_list(s, existing_sug):
            existing_sug.append(s)
            counts["new_suggestions_list"].append(s)
    current["automation_suggestions"] = existing_sug[:10]
    current["last_compilation"] = datetime.now().isoformat()

    return counts


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def format_summary(applied, agent_autos_count):
    lines = ["Weekly summary:"]

    np_, rp = applied.get("new_patterns", 0), applied.get("removed_patterns", 0)
    if np_ or rp:
        lines.append(f"- Patterns: +{np_} -{rp}")

    ns = applied.get("new_suggestions_list", [])
    if ns:
        sample = ns[0][:80] if ns[0] else ""
        lines.append(f"- New suggestions: {len(ns)} ({sample}{'...' if len(ns) > 1 else ''})")

    soul_add = applied.get("soul_rules_added", 0)
    soul_rm = applied.get("soul_rules_removed", 0)
    if soul_add or soul_rm:
        lines.append(f"- Soul: +{soul_add} -{soul_rm} rule(s)")

    pa, pr = applied.get("pending_added", 0), applied.get("pending_removed", 0)
    if pa or pr:
        lines.append(f"- Pending: +{pa} -{pr}")

    uc = applied.get("users_summary", "")
    if uc:
        lines.append(f"- Users: {uc}")

    if len(lines) == 1:
        lines.append("- No relevant changes this week.")

    lines.append(f"- Active agent automations: {agent_autos_count}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_arg(arg, name):
    if not arg or arg.strip() in ("", "{}", "[]", "null"):
        return None
    try:
        return json.loads(arg.strip())
    except (ValueError, json.JSONDecodeError) as e:
        print(f"WARNING: {name} invalid ({e}) - skipping this block.", file=sys.stderr)
        return None


def main():
    if len(sys.argv) < 4:
        print("Usage: weekly_compile.py '<soul_json>' '<users_json>' '<insights_json>'")
        sys.exit(1)

    soul_changes = parse_arg(sys.argv[1], "soul_json")
    users_changes_raw = parse_arg(sys.argv[2], "users_json")
    insights_changes = parse_arg(sys.argv[3], "insights_json")

    insights_path = os.path.join(MEMORY_DIR, "insights.json")
    soul_path = os.path.join(MEMORY_DIR, "soul.json")
    users_path = os.path.join(MEMORY_DIR, "users.json")

    backup_file(insights_path)
    backup_file(soul_path)
    backup_file(users_path)

    applied = {
        "new_patterns": 0, "removed_patterns": 0,
        "new_suggestions_list": [],
        "soul_rules_added": 0, "soul_rules_removed": 0,
        "pending_added": 0, "pending_removed": 0,
        "users_summary": "",
    }

    # v7.3-B.2 — each file mutated with locked_update (separate locks)
    if soul_changes and isinstance(soul_changes, dict):
        with locked_update(soul_path) as soul:
            added, removed = apply_soul(soul, soul_changes)
            applied["soul_rules_added"] = added
            applied["soul_rules_removed"] = removed

    if users_changes_raw:
        if isinstance(users_changes_raw, str):
            users_changes_raw = parse_arg(users_changes_raw, "users_json_inner")
        if isinstance(users_changes_raw, dict):
            with locked_update(users_path) as users:
                applied["users_summary"] = apply_users(users, users_changes_raw)

    if insights_changes and isinstance(insights_changes, dict):
        with locked_update(
            insights_path,
            default={"detected_patterns": [], "pending": [], "automation_suggestions": []}
        ) as insights:
            ins_counts = apply_insights(insights, insights_changes)
            applied["new_patterns"] = ins_counts["new_patterns"]
            applied["removed_patterns"] = ins_counts["removed_patterns"]
            applied["pending_added"] = ins_counts["pending_added"]
            applied["pending_removed"] = ins_counts["pending_removed"]
            applied["new_suggestions_list"] = ins_counts["new_suggestions_list"]

    print(format_summary(applied, count_agent_automations()))


if __name__ == "__main__":
    main()
