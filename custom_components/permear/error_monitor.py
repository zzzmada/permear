"""Real-time error monitor, in-process (v9.0-final).

Replaces the shell chain infrastructure.yaml error automation +
process_log_event.py + lib/logs.py + manage_archived.py.

Listens to HA's system_log_event bus events (level ERROR) and applies the
production pipeline: NOISY filter → 24h-archived check → provider-transient
check (503/UNAVAILABLE/429/RESOURCE_EXHAUSTED + connection resets) →
SELF/HA classification → direct Telegram card with a "Silenciar 24h" button.

Errors NEVER enter the event buffer or ARAS (rule: errors are not household
events). Health stays 2 states — archiving feeds sensor.permear_health's
erros_silenciados_ativos attribute through the same archived_errors.json
(flock-shared with the shell during coexistence).

Flood guard: max 5 cards per 10-minute rolling window (ports the shell's
queued/max:5 + 10-min tail delay); excess errors are only logged.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections import deque
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import (
    ARCHIVED_ERRORS_RELATIVE_PATH,
    DOMAIN,
    ERROR_ARCHIVE_EXPIRATION_HOURS,
    ERROR_CARD_MAX_PER_WINDOW,
    ERROR_CARD_WINDOW_SECONDS,
    NOISY_COMPONENTS,
    SELF_COMPONENTS,
    TRANSIENT_MSG_KEYWORDS,
)
from .notify import async_send_telegram
from .storage import load_json, locked_json_update

_LOGGER = logging.getLogger(__name__)

# HA error messages occasionally carry credentials in tracebacks/URLs —
# redact before anything leaves the device for Telegram.
_REDACT_PATTERNS = (
    # Bearer first — "Authorization: Bearer <jwt>" must not leave the jwt
    # behind after the key=value pattern consumes only the word "Bearer"
    (re.compile(r"Bearer\s+\S+", re.IGNORECASE), "[redacted]"),
    (
        re.compile(
            r"(token|api[_-]?key|password|secret|authorization)\s*[=:]\s*\S+",
            re.IGNORECASE,
        ),
        r"\1=[redacted]",
    ),
    # strip query strings from URLs (tokens often travel there)
    (re.compile(r"(https?://[^\s?]+)\?\S+"), r"\1?[redacted]"),
)


def redact_secrets(message: str) -> str:
    for pat, repl in _REDACT_PATTERNS:
        message = pat.sub(repl, message)
    return message


def is_provider_transient(component: str, message: str) -> bool:
    """Expected transient errors — LLM 503/429 quota and device connections."""
    comp = component.lower()
    msg = message.lower()
    if "google_generative_ai" in comp and (
        "503" in msg or "unavailable" in msg
        or "429" in msg or "resource_exhausted" in msg
    ):
        return True
    return any(kw in msg for kw in TRANSIENT_MSG_KEYWORDS)


def compute_hash(component: str, message: str) -> str:
    """Stable 8-char signature: MD5(component | first 100 chars)."""
    sig = f"{component.lower()}|{message[:100]}"
    return hashlib.md5(sig.encode("utf-8")).hexdigest()[:8]


def _cleanup_expired(state: dict) -> dict:
    now = datetime.now()
    keep = {}
    for h, info in state.get("errors", {}).items():
        try:
            if now < datetime.fromisoformat(info["expires_at"]):
                keep[h] = info
        except (ValueError, KeyError, TypeError):
            continue
    state["errors"] = keep
    return state


def archive_error(hass: HomeAssistant, hash_val: str, component: str,
                  message_preview: str) -> str:
    """Silence an error signature for 24h (ports manage_archived archive).
    Executor only. Returns the PT confirmation text."""
    now = datetime.now()
    expires = now + timedelta(hours=ERROR_ARCHIVE_EXPIRATION_HOURS)
    path = hass.config.path(ARCHIVED_ERRORS_RELATIVE_PATH)
    with locked_json_update(path, {"errors": {}}) as state:
        _cleanup_expired(state)
        state.setdefault("errors", {})[hash_val] = {
            "component": component,
            "message_preview": message_preview[:100],
            "archived_at": now.isoformat(),
            "expires_at": expires.isoformat(),
        }
    return f"Silenciado até {expires.strftime('%d/%m %H:%M')}"


class PermearErrorMonitor:
    """system_log_event listener → filtered Telegram error cards."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._unsub = None
        self._sent_at: deque = deque()

    @callback
    def start(self) -> None:
        self._unsub = self._hass.bus.async_listen(
            "system_log_event", self._on_log_event
        )
        self._check_fire_event()
        _LOGGER.info("Error monitor listening to system_log_event")

    @callback
    def _check_fire_event(self) -> None:
        """system_log only fires the event with `fire_event: true` in YAML —
        without it the monitor is a silent no-op. Raise a Repair issue."""
        handler = self._hass.data.get("system_log")
        fire_event = getattr(handler, "fire_event", None)
        if fire_event is False:
            _LOGGER.warning(
                "system_log fire_event is disabled — the PERMEAR error "
                "monitor will receive no events. Add 'system_log: "
                "fire_event: true' to configuration.yaml."
            )
            ir.async_create_issue(
                self._hass,
                DOMAIN,
                "system_log_fire_event",
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="system_log_fire_event",
            )
        else:
            # enabled, or undetectable (handler API drift) — no issue
            ir.async_delete_issue(self._hass, DOMAIN, "system_log_fire_event")

    @callback
    def stop(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    async def _on_log_event(self, event) -> None:
        try:
            await self._process(event)
        except Exception:  # noqa: BLE001 — the monitor must never crash HA
            _LOGGER.exception("Error monitor failed processing a log event")

    async def _process(self, event) -> None:
        data = event.data or {}
        if str(data.get("level", "")).upper() != "ERROR":
            return

        component = str(data.get("name") or "unknown")
        raw_msg = data.get("message")
        if isinstance(raw_msg, (list, tuple)):  # system_log sends a list
            message = " ".join(str(m) for m in raw_msg)
        else:
            message = str(raw_msg or "")
        message = redact_secrets(message)[:200]
        comp_lower = component.lower()

        # Filter 1: NOISY components never reach the user
        if any(noisy in comp_lower for noisy in NOISY_COMPONENTS):
            return

        err_hash = compute_hash(component, message)

        # Filter 2: silenced for 24h via the card button
        archived = await self._hass.async_add_executor_job(
            self._is_archived, err_hash
        )
        if archived:
            return

        # Filter 3: provider/connection transients — retry/fallback resolves
        if is_provider_transient(component, message):
            return

        # Flood guard (replaces queued max:5 + 10-min delay)
        now = datetime.now().timestamp()
        while self._sent_at and now - self._sent_at[0] > ERROR_CARD_WINDOW_SECONDS:
            self._sent_at.popleft()
        if len(self._sent_at) >= ERROR_CARD_MAX_PER_WINDOW:
            _LOGGER.warning("Error card suppressed (flood guard): %s - %s",
                            component, message[:80])
            return
        self._sent_at.append(now)

        is_self = any(sc in comp_lower for sc in SELF_COMPONENTS)
        prefix = "ERRO PROPRIO" if is_self else "ERRO HA"
        await async_send_telegram(
            self._hass,
            f"{prefix}: {component} - {message}\n[id:{err_hash}]",
            inline_keyboard=["Silenciar 24h:/Silenciar"],
        )

    def _is_archived(self, hash_val: str) -> bool:
        path = self._hass.config.path(ARCHIVED_ERRORS_RELATIVE_PATH)
        state = _cleanup_expired(load_json(path, {"errors": {}}))
        return hash_val in state.get("errors", {})
