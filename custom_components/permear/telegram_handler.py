"""Telegram conversation handler + callbacks, in-process (v9.0-final).

Replaces automations/telegram.yaml (7 automations, 977 lines) + the dedup,
priority, spec and entity-list helper scripts. One class, three bus
listeners (telegram_text / telegram_callback / telegram_command), one
in-memory state machine.

State machine (was input_text.permear_pending_auto_spec + a JSON file):
  ""             → regular conversation
  awaiting_new   → next text is an automation description → ai_task spec
  awaiting_edit  → next text edits the pending spec → ai_task spec
  pending        → a built spec waits for sim/não or the card buttons
The state now lives in memory — an HA restart simply drops an unfinished
proposal (transient conversation state, nothing persistent lost).

Conversation goes to the 'conversation' provider of the config entry
(conversation.process, with tools — NEVER ai_task), 3 retries (0/15/45s),
then the conversation_fallback with the same retries; both failing → honest
PT error, no degraded mode (Reading B). Internal agent tokens (LIST_AUTOS,
REMOVE_AUTO) are intercepted and never reach the user. Dedup by message_id
(in-memory, 24h TTL — replaces the daily_ DB flags). User replies mark the
last 15 min of emits as reacted (engagement signal).

User-facing text PT, plain_text, chat_id from the config entry (notify.py).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

from homeassistant.core import HomeAssistant, callback

from .agent_automations import (
    AgentAutomations,
    build_spec,
    describe_action,
    describe_trigger,
)
from .config import PermearConfig
from .const import (
    CONVERSATION_RETRY_DELAYS,
    MONITORED_ENTITIES_RELATIVE_PATH,
    REACTION_WINDOW_MINUTES,
    SPEC_ENTITY_DOMAINS,
    TELEGRAM_CONFIRM_WORDS,
    TELEGRAM_DEDUP_TTL_SECONDS,
    TELEGRAM_REJECT_WORDS,
)
from .error_monitor import archive_error
from .household import agent_preamble
from .llm import AiTaskClient
from .notify import (
    async_answer_callback,
    async_edit_message,
    async_send_telegram,
    async_set_last_message,
)
from .storage import PermearStorage, load_json, locked_json_update
from .updates import PermearUpdates

_LOGGER = logging.getLogger(__name__)

_AUTO_REQUEST_KEYWORDS = (
    "automação", "automacao", "criar auto", "crie auto",
    "remove auto", "remova auto", "list auto",
)
_LIST_KEYWORDS = (
    "listar automacao", "listar automações",
    "minhas automacoes", "minhas automações",
)
_INTERNAL_TOKENS = ("LIST_AUTOS", "NO_AUTOMATIONS", "CREATE_AUTO:", "REMOVE_AUTO:")
_CONV_ERROR_MARKERS = ("Sorry, I had a problem", "503", "UNAVAILABLE")

SPEC_STRUCTURE = {
    "alias": {
        "description": "Nome curto da automacao em PT-BR. Vazio se impossivel de mapear.",
        "required": True,
        "selector": {"text": {}},
    },
    "trigger_type": {
        "description": "Tipo do gatilho: time, state, numeric_state ou time_pattern",
        "required": True,
        "selector": {"select": {"options": ["time", "state", "numeric_state", "time_pattern"]}},
    },
    "trigger_config": {
        "description": 'JSON string do trigger compativel com HA. Ex: {"platform":"time","at":"18:00:00"}',
        "required": True,
        "selector": {"text": {}},
    },
    "action_service": {
        "description": "Service HA. Ex: light.turn_on, switch.turn_on, climate.turn_on, cover.open_cover, media_player.turn_on",
        "required": True,
        "selector": {"text": {}},
    },
    "action_entity": {
        "description": "Entity ID da lista de entidades disponiveis. Use EXATAMENTE o entity_id da lista.",
        "required": True,
        "selector": {"text": {}},
    },
    "condition_text": {
        "description": "Condicao em linguagem natural ou vazio",
        "required": False,
        "selector": {"text": {}},
    },
}


class PermearTelegramHandler:
    """Bus listeners + state machine for the Telegram surface."""

    def __init__(
        self,
        hass: HomeAssistant,
        storage: PermearStorage,
        config: PermearConfig,
        llm: AiTaskClient,
        autos: AgentAutomations,
        updates: PermearUpdates,
    ) -> None:
        self._hass = hass
        self._storage = storage
        self._config = config
        self._llm = llm
        self._autos = autos
        self._updates = updates
        self._unsubs: list = []
        self._pending_state = ""
        self._pending_spec: dict | None = None
        self._seen_messages: dict = {}  # message_id -> monotonic-ish ts
        self._context_conv_id: str | None = None  # preamble sent for this conv

    @callback
    def start(self) -> None:
        listen = self._hass.bus.async_listen
        self._unsubs = [
            listen("telegram_text", self._on_text),
            listen("telegram_callback", self._on_callback),
            listen("telegram_command", self._on_command),
        ]
        _LOGGER.info("Telegram handler listening (text/callback/command)")

    @callback
    def stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------

    def _chat_allowed(self, data: dict) -> bool:
        """Single-chat contract: filter on the configured chat_id when set;
        empty config accepts the bot's allowed chat (pre-v9.0 behavior)."""
        configured = self._config.telegram_chat_id
        if not configured:
            return True
        return str(data.get("chat_id", "")) == configured

    def _is_duplicate(self, message_id) -> bool:
        """In-memory dedup by message_id, 24h TTL (replaces telegram_dedup.py)."""
        if not message_id:
            return False
        now = datetime.now().timestamp()
        self._seen_messages = {
            mid: ts for mid, ts in self._seen_messages.items()
            if now - ts < TELEGRAM_DEDUP_TTL_SECONDS
        }
        if message_id in self._seen_messages:
            return True
        self._seen_messages[message_id] = now
        return False

    def _set_state(self, state: str, spec: dict | None) -> None:
        self._pending_state = state
        self._pending_spec = spec

    # ------------------------------------------------------------------
    # telegram_text
    # ------------------------------------------------------------------

    async def _on_text(self, event) -> None:
        try:
            await self._handle_text(event)
        except Exception:  # noqa: BLE001 — the handler must never crash HA
            _LOGGER.exception("Telegram text handling failed")

    async def _handle_text(self, event) -> None:
        data = event.data or {}
        if not self._chat_allowed(data):
            return
        text = str(data.get("text") or "").strip()
        if not text or self._is_duplicate(data.get("message_id")):
            return
        lower = text.lower()

        # sim/não over a built proposal (was the confirm/reject automations)
        if self._pending_state == "pending" and self._pending_spec:
            if lower in TELEGRAM_CONFIRM_WORDS:
                spec = self._pending_spec
                self._set_state("", None)
                result = await self._autos.async_create(spec)
                await async_send_telegram(self._hass, result)
                return
            if lower in TELEGRAM_REJECT_WORDS:
                self._set_state("", None)
                await async_send_telegram(self._hass, "Automação cancelada.")
                return

        await self._storage.async_record_interaction("telegram", text[:100])
        await self._storage.async_mark_reactions(REACTION_WINDOW_MINUTES)

        if any(k in lower for k in _LIST_KEYWORDS):
            await self._send_list_card()
            return

        if self._pending_state in ("awaiting_new", "awaiting_edit"):
            await self._spec_creation_flow(text)
            return

        await self._conversation_flow(text)

    # ------------------------------------------------------------------
    # Automation-spec creation (awaiting_* → ONE ai_task call)
    # ------------------------------------------------------------------

    async def _spec_creation_flow(self, text: str) -> None:
        is_edit = (
            self._pending_state == "awaiting_edit" and self._pending_spec is not None
        )
        entities_text = await self._hass.async_add_executor_job(
            self._monitored_entities_text
        )
        prompt = self._build_spec_prompt(text, entities_text, is_edit)

        data = await self._llm.async_generate(
            "HA automation creation", prompt, SPEC_STRUCTURE
        )
        alias = str((data or {}).get("alias") or "").strip()
        if len(alias) < 3:
            self._set_state("", None)
            await async_send_telegram(
                self._hass,
                "⚠️ Nao consegui interpretar a descricao.\n\n"
                'Tente reformular com mais detalhes, ex:\n'
                '"ligar AC suite todo dia as 18h"',
            )
            return

        spec, error = build_spec(data)
        if spec is None:
            # State stays awaiting — the user can rephrase and retry
            await async_send_telegram(
                self._hass,
                f"❌ Erro ao montar a automacao.\n\n{error[:200]}",
            )
            return

        self._set_state("pending", spec)
        await async_send_telegram(
            self._hass,
            "✨ Nova automacao\n\n"
            f"📌 {spec['alias']}\n\n"
            f"Quando: {describe_trigger(spec)}\n"
            f"O que faz: {describe_action(spec)}",
            inline_keyboard=[
                "Criar:/cnew_confirm, Ajustar:/cedt_request",
                "Descartar:/cdsc_clear",
            ],
        )

    def _build_spec_prompt(self, text: str, entities_text: str, is_edit: bool) -> str:
        if is_edit:
            head = (
                f"Automacao existente (JSON): {json.dumps(self._pending_spec, ensure_ascii=False)}\n\n"
                f'O usuario quer modificar com: "{text}"\n'
                "Produza uma nova especificacao completa aplicando a modificacao solicitada."
            )
        else:
            head = f'Crie uma automacao do Home Assistant baseada na descricao:\n"{text}"'
        return f"""{head}

Regras:
- alias: nome curto em PT-BR, sem aspas especiais
- trigger_type: time | state | numeric_state | time_pattern
- trigger_config: JSON string do trigger no formato HA. Exemplos:
  time: {{"platform":"time","at":"HH:MM:SS"}}
  state: {{"platform":"state","entity_id":"x","to":"estado"}}
  numeric_state: {{"platform":"numeric_state","entity_id":"sensor.x","above":N}}
  time_pattern: {{"platform":"time_pattern","hours":"/1"}}
- action_service: domain.servico (ex: light.turn_on, climate.turn_on, switch.turn_on, switch.turn_off, cover.open_cover, cover.close_cover, media_player.turn_on)
- action_entity: use SOMENTE entity_ids da lista abaixo — nenhum outro sera aceito
- condition_text: condicao em linguagem natural ou deixe vazio

Entidades disponiveis nesta casa (use EXATAMENTE estes entity_ids):
{entities_text}

Se a descricao nao mapear para nenhuma entidade da lista, retorne alias vazio."""

    def _monitored_entities_text(self) -> str:
        """Ports get_monitored_entities_text.py — monitored entities grouped
        by domain, skipping entries without a descriptive friendly_name."""
        data = load_json(
            self._hass.config.path(MONITORED_ENTITIES_RELATIVE_PATH),
            {"entities": []},
        )
        by_domain: dict = {}
        for e in data.get("entities", []):
            if not e.get("monitor", False):
                continue
            eid = e.get("entity_id", "")
            domain = eid.split(".")[0] if "." in eid else "outros"
            if domain not in SPEC_ENTITY_DOMAINS:
                continue
            fname = (e.get("friendly_name") or "").strip()
            if not fname or fname == eid:
                continue
            eid_base = eid.split(".", 1)[1].replace("_", " ") if "." in eid else eid
            line = f"  {eid} ({fname})" if fname.lower() != eid_base.lower() else f"  {eid}"
            by_domain.setdefault(domain, []).append(line)
        if not by_domain:
            return "(lista indisponivel)"
        lines = []
        for domain in sorted(by_domain):
            lines.append(f"{domain.upper()}:")
            lines.extend(sorted(by_domain[domain]))
            lines.append("")
        return "\n".join(lines).rstrip()

    # ------------------------------------------------------------------
    # Conversation (provider 'conversation' + fallback — Reading B)
    # ------------------------------------------------------------------

    async def _conversation_flow(self, text: str) -> None:
        conv_id = f"permear_telegram_{datetime.now():%Y%m%d}"  # daily rotation
        prompt = self._build_conversation_prompt(text, conv_id)

        speech = None
        if self._config.conversation:
            speech = await self._converse(self._config.conversation, prompt, conv_id)
        if speech is None and self._config.conversation_fallback:
            speech = await self._converse(
                self._config.conversation_fallback, prompt, conv_id
            )
            if speech is not None:
                # Fallback assumed WITH tools — user doesn't notice (Reading B)
                await self._llm.async_log_fallback()
        if speech is None:
            await self._llm.async_log_fallback()
            await async_send_telegram(
                self._hass,
                "Sistema temporariamente indisponível. Tente em alguns minutos.",
            )
            return
        # Preamble delivered for this conversation — don't repeat it.
        # (Only marked on success: a fully failed call re-injects next time.)
        self._context_conv_id = conv_id

        # Internal agent tokens — intercepted, never shown to the user
        if "REMOVE_AUTO:" in speech:
            ident = speech.split("REMOVE_AUTO:")[1].strip().split("\n")[0].strip()
            await async_send_telegram(self._hass, await self._autos.async_remove(ident))
            return
        if "LIST_AUTOS" in speech:
            await async_send_telegram(self._hass, await self._autos.async_list_text())
            return
        if speech in _INTERNAL_TOKENS or speech.startswith(("CREATE_AUTO:", "REMOVE_AUTO:")):
            await async_send_telegram(
                self._hass,
                "⚠️ Nao consegui responder agora. Tente em alguns instantes.",
            )
            return

        await async_send_telegram(self._hass, speech)
        await async_set_last_message(self._hass, speech)

    def _build_conversation_prompt(self, text: str, conv_id: str) -> str:
        """User turn, optionally prefixed by the PERMEAR context preamble.

        The preamble goes INSIDE the same conversation.process text block as
        the user's turn (first message of each daily conversation) — never a
        fake user/assistant turn, which would corrupt the HA chat-log
        alternation (AGY lesson). The agent needs no hand-pasted UI prompt.
        """
        lower = text.lower()
        resident = self._config.primary_resident or "Morador"
        parts = []
        if conv_id != self._context_conv_id:
            parts.append(agent_preamble(self._hass, self._config))
        if any(k in lower for k in _AUTO_REQUEST_KEYWORDS):
            parts.append(
                "[INSTRUCAO OBRIGATORIA: Responda APENAS com uma linha no "
                "formato exato abaixo, sem nenhum outro texto:\n"
                "Para remover: REMOVE_AUTO: alias\n"
                "Para listar: LIST_AUTOS\n"
                "NAO escreva nada alem dessa linha. NAO confirme, NAO explique.]"
            )
        parts.append(f"[{resident}]: {text}")
        return "\n".join(parts)

    async def _converse(self, agent_id: str, prompt: str, conv_id: str) -> str | None:
        """3 attempts (0/15/45s) against one provider; None = gave up."""
        for delay in CONVERSATION_RETRY_DELAYS:
            if delay:
                await asyncio.sleep(delay)
            try:
                resp = await self._hass.services.async_call(
                    "conversation",
                    "process",
                    {"agent_id": agent_id, "text": prompt,
                     "conversation_id": conv_id},
                    blocking=True,
                    return_response=True,
                )
            except Exception as exc:  # noqa: BLE001
                _LOGGER.warning("conversation.process via %s failed: %s",
                                agent_id, exc)
                continue
            speech = str(
                (((resp or {}).get("response") or {}).get("speech") or {})
                .get("plain", {}).get("speech") or ""
            ).strip()
            if len(speech) >= 5 and not any(m in speech for m in _CONV_ERROR_MARKERS):
                return speech
        return None

    # ------------------------------------------------------------------
    # telegram_command
    # ------------------------------------------------------------------

    async def _on_command(self, event) -> None:
        try:
            data = event.data or {}
            if not self._chat_allowed(data):
                return
            command = str(data.get("command") or "")
            if command == "/nova_automacao":
                await async_send_telegram(
                    self._hass,
                    "Nova automacao\n\n"
                    "Descreva o que ela deve fazer.\n"
                    'Ex: "ligar AC suite as 18h se temperatura passar de 25 graus"',
                )
                self._set_state("awaiting_new", None)
            elif command == "/listar_automacoes":
                await self._send_list_card()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Telegram command handling failed")

    async def _send_list_card(self) -> None:
        listing = await self._autos.async_list()
        autos = listing["automations"][:10]
        if not autos:
            await async_send_telegram(
                self._hass,
                "🤖 Suas automacoes\n\n"
                "Nenhuma automacao criada pelo agente ainda.\n"
                "Use /nova_automacao para criar uma.",
            )
            return
        lines = [f"🤖 Suas automacoes ({listing['count']})", ""]
        lines += [f"{i}. {a['alias']}" for i, a in enumerate(autos, 1)]
        lines += ["", "Toque em Remover N para excluir."]
        keyboard = [
            f"Remover {i}:/drmv_confirm_{a['id']}" for i, a in enumerate(autos, 1)
        ]
        await async_send_telegram(
            self._hass, "\n".join(lines), inline_keyboard=keyboard
        )

    # ------------------------------------------------------------------
    # telegram_callback (inline keyboard buttons)
    # ------------------------------------------------------------------

    async def _on_callback(self, event) -> None:
        try:
            await self._handle_callback(event)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Telegram callback handling failed")

    async def _handle_callback(self, event) -> None:
        data = event.data or {}
        if not self._chat_allowed(data):
            return
        cb_data = str(data.get("data") or "")
        cb_id = data.get("id")
        chat_id = data.get("chat_id")
        message = data.get("message") or {}
        msg_id = message.get("message_id")
        original = str(message.get("text") or "")

        async def answer(text: str) -> None:
            await async_answer_callback(self._hass, cb_id, text)

        async def edit(text: str) -> None:
            if msg_id is not None:
                await async_edit_message(self._hass, chat_id, msg_id, text)

        if "Silenciar" in cb_data:
            err_hash = self._extract_tag(original, "[id:")
            if not err_hash:
                return
            preview = original.replace("'", "")[:80]
            await self._hass.async_add_executor_job(
                archive_error, self._hass, err_hash, "auto", preview
            )
            await answer("Silenciado por 24h")
            await edit(f"{original}\n[silenciado 24h]")

        elif "Atualizar" in cb_data:
            entity = self._extract_tag(original, "[entity:")
            if not entity:
                return
            await answer("Iniciando atualização...")
            result = await self._updates.async_execute(entity)
            await edit(f"{original}\n\n[INICIADO]\n{result}")

        elif "Ignorar" in cb_data:
            entity = self._extract_tag(original, "[entity:")
            if not entity:
                return
            result = await self._updates.async_skip(entity)
            await answer("Ignorado ate nova versao")
            await edit(f"{original}\n[ignorado]")

        elif "cnew_" in cb_data:
            await answer("Criando...")
            spec = self._pending_spec
            self._set_state("", None)
            if spec is None:
                await edit(f"{original}\n\nNenhuma proposta pendente.")
                return
            result = await self._autos.async_create(spec)
            await edit(f"{original}\n\n{result}")

        elif "cedt_" in cb_data:
            await answer("Aguardando ajuste...")
            self._pending_state = "awaiting_edit"  # keep the spec for context
            await edit(f"{original}\n\nAjustar — me diga o que mudar.")

        elif "cdsc_" in cb_data:
            await answer("Descartada")
            self._set_state("", None)
            await edit(f"{original}\n\nDescartada.")

        elif "drmv_confirm_" in cb_data:
            ident = cb_data.split("drmv_confirm_")[1]
            result = await self._autos.async_remove(ident)
            await answer("Removida")
            await edit(result)

        elif cb_data.startswith("/prio_set_"):
            payload = cb_data.replace("/prio_set_", "")
            nivel_s, _, entity = payload.partition("_")
            try:
                nivel = int(nivel_s)
            except ValueError:
                return
            await self._hass.async_add_executor_job(
                self._set_entity_priority, entity, nivel
            )
            await answer("Prioridade definida")
            if nivel == 2:
                detail = "Você será avisado sempre que este sensor disparar."
            elif nivel == 1:
                detail = "Você será avisado só em situações anormais."
            else:
                detail = "Sensor ignorado nos alertas."
            await edit(f"{original}\n\nPrioridade definida: nivel {nivel}.\n{detail}")

        else:
            _LOGGER.debug("Unhandled telegram callback: %s", cb_data)

    @staticmethod
    def _extract_tag(text: str, prefix: str) -> str:
        """'… [id:abc123]' → 'abc123' (also used for [entity:…])."""
        if prefix not in text:
            return ""
        return text.split(prefix)[1].split("]")[0].strip()

    def _set_entity_priority(self, entity_id: str, priority: int) -> None:
        """Ports set_entity_priority.py — human curation, source='user'
        (never overwritten by engagement or memory, rule #31)."""
        path = self._hass.config.path(MONITORED_ENTITIES_RELATIVE_PATH)
        with locked_json_update(path, {"entities": []}) as data:
            for e in data.get("entities", []):
                if e.get("entity_id") == entity_id:
                    e["priority"] = priority
                    e["priority_source"] = "user"
                    return
            data.setdefault("entities", []).append({
                "entity_id": entity_id,
                "monitor": True,
                "priority": priority,
                "priority_source": "user",
            })
