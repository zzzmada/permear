"""Deterministic event co-occurrence detector (v8.6 contract, in-process v8.10).

Ported from scripts/correlate_events.py. PURE — no DB, no I/O, no LLM. The
caller (Systems Consolidation) fetches event_log rows via storage and passes
them in; this module only computes.

Contract (rule #45):
  - pair = (entity_a, entity_b), a < b, events <= 120s apart on the SAME day
  - candidate requires >= 3 DISTINCT DAYS (not total count — rejects
    single-day bursts from flapping devices)
  - invalid entity_ids ignored (NULL, '-', 'while', 'mesmo', empty, no '.')
  - output sorted by dias DESC, ocorrencias DESC
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from .const import COOCCURRENCE_MIN_DISTINCT_DAYS, COOCCURRENCE_WINDOW_SECONDS

_INVALID_ENTITY_IDS = frozenset({"-", "while", "mesmo", ""})


def is_valid_entity_id(eid) -> bool:
    if eid is None:
        return False
    eid = eid.strip()
    if not eid or eid in _INVALID_ENTITY_IDS:
        return False
    return "." in eid


def _ts_to_seconds(ts_str: str) -> float:
    ts_str = ts_str[:26]
    try:
        dt = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S.%f")
    except ValueError:
        dt = datetime.strptime(ts_str[:19], "%Y-%m-%dT%H:%M:%S")
    return dt.timestamp()


def compute_pairs(events: list[dict]) -> list[dict]:
    """Co-occurring entity pairs within the window, on >= 3 distinct days.

    events: event_log rows ({ts, entity_id, ...}); invalid ids are skipped.
    Returns [{a, b, dias, ocorrencias}] sorted by dias DESC, ocorrencias DESC.
    """
    by_date: dict[str, list] = defaultdict(list)
    for ev in events:
        if not is_valid_entity_id(ev.get("entity_id")):
            continue
        ts = ev.get("ts") or ""
        try:
            ts_sec = _ts_to_seconds(ts)
        except ValueError:
            continue
        by_date[ts[:10]].append((ts_sec, ev["entity_id"]))

    pair_days: dict[tuple, set] = defaultdict(set)
    pair_count: dict[tuple, int] = defaultdict(int)

    for dia, evts in by_date.items():
        evts_sorted = sorted(evts, key=lambda x: x[0])
        n = len(evts_sorted)
        for i in range(n):
            ts_i, eid_i = evts_sorted[i]
            for j in range(i + 1, n):
                ts_j, eid_j = evts_sorted[j]
                if ts_j - ts_i > COOCCURRENCE_WINDOW_SECONDS:
                    break  # events are sorted — nothing further pairs with i
                if eid_i == eid_j:
                    continue
                a, b = (eid_i, eid_j) if eid_i < eid_j else (eid_j, eid_i)
                pair_days[(a, b)].add(dia)
                pair_count[(a, b)] += 1

    result = [
        {"a": a, "b": b, "dias": len(dias_set), "ocorrencias": pair_count[(a, b)]}
        for (a, b), dias_set in pair_days.items()
        if len(dias_set) >= COOCCURRENCE_MIN_DISTINCT_DAYS
    ]
    result.sort(key=lambda x: (-x["dias"], -x["ocorrencias"]))
    return result
