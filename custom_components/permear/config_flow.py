"""Config flow for PERMEAR (v9.0) — full UI configuration, single instance.

Install step (config_flow → entry.data): the 4 AI provider entities
(conversation.* / ai_task.*) and the optional Telegram chat_id (empty →
telegram_bot uses the first allowed chat, same behavior as before).

Options flow (→ entry.options): ARAS sensitivity (the ONLY ARAS knob),
primary resident, and the cycle schedules. Saving options reloads the entry
(update listener in __init__.py) so the cycles pick the new values without a
restart. The old /config/permear.yaml is never read — no migration.
"""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TimeSelector,
)

from .const import (
    CONF_AGENT_NAME,
    CONF_CHAT_ID,
    CONF_CONVERSATION,
    CONF_CONVERSATION_FALLBACK,
    CONF_DATA,
    CONF_DATA_FALLBACK,
    CONF_HEARTBEAT_END,
    CONF_HEARTBEAT_START,
    CONF_PRIMARY_RESIDENT,
    CONF_SENSITIVITY,
    CONF_SLEEP_TIME,
    CONF_SYSTEMS_TIME,
    CONF_VOICE_SCRIPT,
    DEFAULT_HEARTBEAT_END,
    DEFAULT_HEARTBEAT_START,
    DEFAULT_SENSITIVITY,
    DEFAULT_SLEEP_TIME,
    DEFAULT_SYSTEMS_TIME,
    DOMAIN,
    SENSITIVITY_MAP,
)
from .household import get_resident_names

_CHAT_ID_RE = re.compile(r"^-?\d+$")

_PROVIDER_FIELDS = (
    (CONF_CONVERSATION, "conversation"),
    (CONF_DATA, "ai_task"),
    (CONF_CONVERSATION_FALLBACK, "conversation"),
    (CONF_DATA_FALLBACK, "ai_task"),
)

USER_SCHEMA = vol.Schema(
    {
        **{
            vol.Required(field): EntitySelector(EntitySelectorConfig(domain=domain))
            for field, domain in _PROVIDER_FIELDS
        },
        vol.Optional(CONF_CHAT_ID, default=""): TextSelector(),
    }
)

def _options_schema(resident_options: list[str]) -> vol.Schema:
    """Options schema — primary_resident is a dropdown of the HA person
    entities (custom_value allows a free-text resident without a person).
    RODADA E: the 4 AI providers + Telegram chat_id are reconfigurable here
    (suggested with the current value); providers stay Required so a blank can
    never zero them, and config.py also falls back to entry.data defensively."""
    return vol.Schema(
        {
            **{
                vol.Required(field): EntitySelector(EntitySelectorConfig(domain=domain))
                for field, domain in _PROVIDER_FIELDS
            },
            vol.Optional(CONF_CHAT_ID, default=""): TextSelector(),
            vol.Required(CONF_SENSITIVITY, default=DEFAULT_SENSITIVITY): SelectSelector(
                SelectSelectorConfig(
                    options=sorted(SENSITIVITY_MAP),
                    mode=SelectSelectorMode.DROPDOWN,
                    translation_key="sensitivity",
                )
            ),
            vol.Optional(CONF_PRIMARY_RESIDENT, default=""): SelectSelector(
                SelectSelectorConfig(
                    options=resident_options,
                    mode=SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            ),
            vol.Required(CONF_HEARTBEAT_START, default=DEFAULT_HEARTBEAT_START): TimeSelector(),
            vol.Required(CONF_HEARTBEAT_END, default=DEFAULT_HEARTBEAT_END): TimeSelector(),
            vol.Required(CONF_SLEEP_TIME, default=DEFAULT_SLEEP_TIME): TimeSelector(),
            vol.Required(CONF_SYSTEMS_TIME, default=DEFAULT_SYSTEMS_TIME): TimeSelector(),
            # Brand-agnostic surface (v9.x): empty agent_name → neutral name;
            # empty voice_script → no voice. Both free text (a service id).
            vol.Optional(CONF_AGENT_NAME, default=""): TextSelector(),
            vol.Optional(CONF_VOICE_SCRIPT, default=""): TextSelector(),
        }
    )

DEFAULT_OPTIONS = {
    CONF_SENSITIVITY: DEFAULT_SENSITIVITY,
    CONF_PRIMARY_RESIDENT: "",
    CONF_HEARTBEAT_START: DEFAULT_HEARTBEAT_START,
    CONF_HEARTBEAT_END: DEFAULT_HEARTBEAT_END,
    CONF_SLEEP_TIME: DEFAULT_SLEEP_TIME,
    CONF_SYSTEMS_TIME: DEFAULT_SYSTEMS_TIME,
    CONF_AGENT_NAME: "",
    CONF_VOICE_SCRIPT: "",
}


def _normalize_times(data: dict[str, Any]) -> dict[str, Any]:
    """TimeSelector returns 'HH:MM:SS' — store the canonical 'HH:MM'."""
    out = dict(data)
    for key in (CONF_HEARTBEAT_START, CONF_HEARTBEAT_END,
                CONF_SLEEP_TIME, CONF_SYSTEMS_TIME):
        if isinstance(out.get(key), str):
            out[key] = out[key][:5]
    return out


class PermearConfigFlow(ConfigFlow, domain=DOMAIN):
    """Single-instance install flow: providers + Telegram chat_id."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors: dict[str, str] = {}
        if user_input is not None:
            for field, _domain in _PROVIDER_FIELDS:
                if self.hass.states.get(user_input[field]) is None:
                    errors[field] = "entity_not_found"
            chat_id = (user_input.get(CONF_CHAT_ID) or "").strip()
            if chat_id and not _CHAT_ID_RE.match(chat_id):
                errors[CONF_CHAT_ID] = "invalid_chat_id"
            if not errors:
                user_input[CONF_CHAT_ID] = chat_id
                return self.async_create_entry(
                    title="PERMEAR", data=user_input, options=DEFAULT_OPTIONS
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                USER_SCHEMA, user_input or {}
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PermearOptionsFlow:
        return PermearOptionsFlow()


class PermearOptionsFlow(OptionsFlow):
    """Sensitivity, primary resident and cycle schedules — no reinstall."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            # RODADA E: validate the (now editable) providers + chat_id, reusing
            # the same error keys as the install flow.
            for field, _domain in _PROVIDER_FIELDS:
                if self.hass.states.get(user_input.get(field, "")) is None:
                    errors[field] = "entity_not_found"
            chat_id = (user_input.get(CONF_CHAT_ID) or "").strip()
            if chat_id and not _CHAT_ID_RE.match(chat_id):
                errors[CONF_CHAT_ID] = "invalid_chat_id"
            if not errors:
                user_input[CONF_CHAT_ID] = chat_id
                return self.async_create_entry(data=_normalize_times(user_input))

        residents = get_resident_names(self.hass)
        current = {**DEFAULT_OPTIONS, **self.config_entry.options}
        # Seed the provider + chat_id suggestions from entry.data when options
        # has not stored them yet (first time the flow is opened).
        for key in (CONF_CONVERSATION, CONF_DATA, CONF_CONVERSATION_FALLBACK,
                    CONF_DATA_FALLBACK, CONF_CHAT_ID):
            if not current.get(key):
                current[key] = self.config_entry.data.get(key, "")
        # Default: first person.* when nothing is configured yet
        if not current.get(CONF_PRIMARY_RESIDENT) and residents:
            current[CONF_PRIMARY_RESIDENT] = residents[0]
        # Keep the user's failed attempt visible on error
        if user_input is not None:
            current = {**current, **user_input}
        # Keep a stored free-text resident selectable in the dropdown
        stored = current.get(CONF_PRIMARY_RESIDENT, "")
        options = residents + ([stored] if stored and stored not in residents else [])
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                _options_schema(options), current
            ),
            errors=errors,
        )
