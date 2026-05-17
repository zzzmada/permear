"""
v7.0 — HA log processing and error classification.

Functions:
- is_provider_transient: detects transient LLM agent errors (503/UNAVAILABLE)
- compute_hash: stable hash of error signature
- is_archived: checks archived_errors via subprocess
- emit: prints structured JSON
- process_event: complete log event processing pipeline
"""
import sys
import os
import json
import hashlib
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from permear_config import NOISY_COMPONENTS, SELF_COMPONENTS

ARCHIVE_SCRIPT = "/config/scripts/manage_archived.py"
CIRCUIT_SCRIPT = "/config/scripts/circuit_breaker.py"


def is_provider_transient(component, message):
    """Detects 503/UNAVAILABLE from LLM agent — silenced because retry resolves."""
    comp = component.lower()
    msg = message.lower()
    is_agent = (
        "google_generative_ai" in comp
        or "google_ai" in comp
        or "openrouter" in comp
        or "deepseek" in comp
    )
    is_transient = "503" in msg or "unavailable" in msg
    return is_agent and is_transient


def compute_hash(component, message):
    """Stable 8-char hash based on (component, first 100 chars)."""
    sig = f"{component.lower()}|{message[:100]}"
    return hashlib.md5(sig.encode("utf-8")).hexdigest()[:8]


def is_archived(hash_val):
    """Query manage_archived.py to check if hash is silenced for 24h."""
    try:
        result = subprocess.run(
            ["python3", ARCHIVE_SCRIPT, "is_archived", hash_val],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() == "YES"
    except Exception:
        return False


def emit(silenced, hash_val="", message="", reason=""):
    """Print result as structured JSON for the automation to parse."""
    print(json.dumps({
        "silenced": silenced,
        "hash": hash_val,
        "message": message,
        "reason": reason,
    }, ensure_ascii=False))


def process_event(component, message):
    """
    Complete log event processing pipeline.
    Applies filters NOISY -> archived -> transient -> classifies SELF/HA.
    """
    if not component:
        emit(True, reason="missing_args")
        return

    message = message[:200]
    comp_lower = component.lower()

    # Filter 1: NOISY components
    for noisy in NOISY_COMPONENTS:
        if noisy in comp_lower:
            emit(True, reason="noisy")
            return

    err_hash = compute_hash(component, message)

    # Filter 2: archived (silenced by user)
    if is_archived(err_hash):
        emit(True, hash_val=err_hash, reason="archived")
        return

    # Filter 3: provider transient 503/UNAVAILABLE — retry will resolve
    if is_provider_transient(component, message):
        try:
            subprocess.run(
                ["python3", CIRCUIT_SCRIPT, "log_503"],
                capture_output=True, timeout=3
            )
        except Exception:
            pass
        emit(True, hash_val=err_hash, reason="provider_transient")
        return

    # Classification
    is_self = any(sc in comp_lower for sc in SELF_COMPONENTS)
    prefix = "SELF_ERROR" if is_self else "HA_ERROR"
    formatted = f"{prefix}: {component} - {message}"

    emit(False, hash_val=err_hash, message=formatted, reason="ok")
