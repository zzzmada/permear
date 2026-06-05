"""
v7.0 — HA log processing and error classification.

Functions:
- is_provider_transient: detects transient agent errors (503/UNAVAILABLE)
- compute_hash: stable hash of an error signature
- is_archived: queries archived_errors via subprocess
- emit: prints structured JSON
- process_event: full log-event processing pipeline
"""
import sys
import os
import json
import hashlib
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from permear_config import NOISY_COMPONENTS, SELF_COMPONENTS

ARCHIVE_SCRIPT = "/config/scripts/manage_archived.py"


TRANSIENT_MSG_KEYWORDS = [
    "clientconnectionreseterror",
    "cannot write to closing transport",
    "connectionreseterror",
]


def is_provider_transient(component, message):
    """Detect expected transient errors — LLM 503 and device connections."""
    comp = component.lower()
    msg = message.lower()
    # LLM 503/UNAVAILABLE/429 (Gemini quota + transient — handled by fallback)
    if "google_generative_ai" in comp and (
        "503" in msg or "unavailable" in msg
        or "429" in msg or "resource_exhausted" in msg
    ):
        return True
    # Transient WebSocket/TCP connection errors (TV, media players, etc.)
    if any(kw in msg for kw in TRANSIENT_MSG_KEYWORDS):
        return True
    return False


def compute_hash(component, message):
    """Stable 8-char hash based on (component, first 100 chars)."""
    sig = f"{component.lower()}|{message[:100]}"
    return hashlib.md5(sig.encode("utf-8")).hexdigest()[:8]


def is_archived(hash_val):
    """Ask manage_archived.py whether the hash is in the 24h-silenced list."""
    try:
        result = subprocess.run(
            ["python3", ARCHIVE_SCRIPT, "is_archived", hash_val],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() == "YES"
    except Exception:
        return False


def emit(silenced, hash_val="", message="", reason=""):
    """Print the result as structured JSON for the automation to parse."""
    print(json.dumps({
        "silenced": silenced,
        "hash": hash_val,
        "message": message,
        "reason": reason,
    }, ensure_ascii=False))


def process_event(component, message):
    """
    Full log-event processing pipeline.
    Applies NOISY → archived → transient filters → classifies SELF/HA.
    """
    if not component:
        emit(True, reason="missing_args")
        return

    message = message[:200]
    comp_lower = component.lower()

    # Filter 1: NOISY
    for noisy in NOISY_COMPONENTS:
        if noisy in comp_lower:
            emit(True, reason="noisy")
            return

    err_hash = compute_hash(component, message)

    # Filter 2: archived
    if is_archived(err_hash):
        emit(True, hash_val=err_hash, reason="archived")
        return

    # Filter 3: provider 503/UNAVAILABLE — transient, retry resolves it
    if is_provider_transient(component, message):
        emit(True, hash_val=err_hash, reason="gemini_transient")
        return

    # Classification
    is_self = any(sc in comp_lower for sc in SELF_COMPONENTS)
    prefix = "ERRO PROPRIO" if is_self else "ERRO HA"
    formatted = f"{prefix}: {component} - {message}"

    emit(False, hash_val=err_hash, message=formatted, reason="ok")
