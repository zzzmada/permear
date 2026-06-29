"""Telegram delivery for the PERMEAR cycles (v8.10).

User-facing text is PT. parse_mode plain_text (rule #4). chat_id comes from
the config entry (v9.0); when empty, telegram_bot falls back to the first
allowed chat — the pre-v9.0 single-chat behavior. Looked up via hass.data so
the cycle callers stay untouched (single instance).
Best-effort: delivery failures are logged, never raised into a cycle.
"""

from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.core import HomeAssistant

from .const import DOMAIN, PENDING_MESSAGE_PATH
from .storage import load_json, locked_json_update

_LOGGER = logging.getLogger(__name__)

LAST_MESSAGE_ENTITY = "input_text.permear_last_message"
# Stable drain order (Sleep before Systems when both are pending the same day).
_PENDING_KEYS = ("sleep", "systems")


def _configured_chat_id(hass: HomeAssistant) -> str:
    for entry_data in (hass.data.get(DOMAIN) or {}).values():
        config = entry_data.get("config")
        chat_id = getattr(config, "telegram_chat_id", "") if config else ""
        if chat_id:
            return chat_id
    return ""


async def async_send_telegram(
    hass: HomeAssistant, message: str, inline_keyboard: list[str] | None = None
) -> bool:
    """Send a Telegram message. Returns True on success, False on failure —
    callers that don't care ignore it; the deferred-message drain relies on it
    to keep an entry that failed to deliver."""
    data: dict = {"message": message, "parse_mode": "plain_text"}
    chat_id = _configured_chat_id(hass)
    if chat_id:
        try:
            data["chat_id"] = int(chat_id)
        except ValueError:
            _LOGGER.warning("Invalid telegram_chat_id %r — ignoring", chat_id)
    if inline_keyboard:
        data["inline_keyboard"] = inline_keyboard
    try:
        await hass.services.async_call(
            "telegram_bot", "send_message", data, blocking=True
        )
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("Telegram delivery failed: %s", exc)
        return False
    return True


async def async_defer_message(hass: HomeAssistant, key: str, text: str) -> None:
    """Persist a cycle's Telegram message for deferred delivery (v9.2.2). The
    night cycles (Sleep ~23:30, Systems weekly) write here instead of sending;
    the morning drain (async_drain_pending) delivers it. JSON in memory/ so a
    restart before 08:00 keeps the pending message (an in-memory timer wouldn't)."""
    text = str(text or "").strip()
    if not text:
        return
    path = hass.config.path(PENDING_MESSAGE_PATH)

    def _write() -> None:
        with locked_json_update(path, {}) as data:
            data[key] = {"text": text, "generated_at": datetime.now().isoformat()}

    await hass.async_add_executor_job(_write)


async def async_drain_pending(hass: HomeAssistant) -> None:
    """Deliver any deferred cycle messages and remove the ones that went out.
    A send that fails keeps its entry for the next drain (idempotent, no loss).
    Missing/empty file → no-op."""
    path = hass.config.path(PENDING_MESSAGE_PATH)
    pending = await hass.async_add_executor_job(load_json, path, {})
    if not isinstance(pending, dict) or not pending:
        return
    drained: list[str] = []
    for key in _PENDING_KEYS:
        entry = pending.get(key)
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("text") or "").strip()
        if not text:
            drained.append(key)  # malformed entry → drop, never retry forever
            continue
        if await async_send_telegram(hass, text):
            drained.append(key)
    if not drained:
        return

    def _remove() -> None:
        with locked_json_update(path, {}) as data:
            for k in drained:
                data.pop(k, None)

    await hass.async_add_executor_job(_remove)


async def async_answer_callback(
    hass: HomeAssistant, callback_query_id, message: str
) -> None:
    """Acknowledge an inline-keyboard tap (toast on the user's phone)."""
    try:
        await hass.services.async_call(
            "telegram_bot",
            "answer_callback_query",
            {"callback_query_id": callback_query_id, "message": message},
            blocking=True,
        )
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("answer_callback_query failed: %s", exc)


async def async_edit_message(
    hass: HomeAssistant, chat_id, message_id, message: str
) -> None:
    """Edit a previously sent card in place (chat_id from the callback event)."""
    try:
        await hass.services.async_call(
            "telegram_bot",
            "edit_message",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "message": message,
                "parse_mode": "plain_text",
            },
            blocking=True,
        )
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("edit_message failed: %s", exc)


async def async_speak(hass: HomeAssistant, message: str) -> None:
    """Optional voice hook (v9.x). PERMEAR never decides on its own to speak —
    it only forwards `message` to the user's own voice service when one is
    configured (options → voice_script, e.g. "script.minha_voz"). Empty →
    silence (no call, no error). Unknown service → warning, never raised.

    The configured service is called as a plain service id ("<domain>.<service>")
    with {"message": message}; a user script receives it as a `message`
    variable. The component embeds no voice device of its own — this hook is the
    only voice surface.
    """
    voice_script = ""
    for entry_data in (hass.data.get(DOMAIN) or {}).values():
        config = entry_data.get("config")
        voice_script = (getattr(config, "voice_script", "") if config else "") or ""
        if voice_script:
            break
    voice_script = voice_script.strip()
    if not voice_script:
        return  # no voice hook configured — stay silent
    if "." not in voice_script:
        _LOGGER.warning(
            "voice_script %r is not a valid service id (expected "
            "'domain.service') — skipping voice", voice_script
        )
        return
    domain, service = voice_script.split(".", 1)
    if not hass.services.has_service(domain, service):
        _LOGGER.warning(
            "voice_script %r not found in Home Assistant — skipping voice",
            voice_script,
        )
        return
    try:
        await hass.services.async_call(
            domain, service, {"message": message}, blocking=False
        )
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("voice_script %r failed: %s", voice_script, exc)


async def async_set_last_message(hass: HomeAssistant, message: str) -> None:
    """Legacy last-message holder — written only when the helper entity
    exists (author setup); public installs have no such input_text."""
    if hass.states.get(LAST_MESSAGE_ENTITY) is None:
        return
    try:
        await hass.services.async_call(
            "input_text",
            "set_value",
            {"entity_id": LAST_MESSAGE_ENTITY, "value": message[:255]},
            blocking=True,
        )
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("last_message update failed: %s", exc)
