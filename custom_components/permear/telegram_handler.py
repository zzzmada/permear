"""Telegram conversation handler + callbacks, in-process (v9.0-final).

Replaces automations/telegram.yaml (7 automations, 977 lines) + the dedup,
priority, spec and entity-list helper scripts. One class, three bus
listeners (telegram_text / telegram_callback / telegram_command), one
in-memory state machine.

State machine (was input_text.permear_pending_auto_spec + a JSON file):
  ""             → regular conversation
  awaiting_new   → next text describes a standing rule → ai_task spec
  awaiting_edit  → next text edits the pending spec → ai_task spec
  pending        → a built spec waits for sim/não or the card buttons
The state now lives in memory — an HA restart simply drops an unfinished
proposal (transient conversation state, nothing persistent lost).

Conversation goes to the 'conversation' provider of the config entry
(conversation.process, with tools — NEVER ai_task), 3 retries (0/15/45s),
then the conversation_fallback with the same retries; both failing → honest
PT error, no degraded mode (Reading B). Internal agent tokens (LIST_AUTOS,
REMOVE_AUTO, CREATE_AUTO) are intercepted and never reach the user. Dedup by message_id
(in-memory, 24h TTL — replaces the daily_ DB flags). User replies mark the
last 15 min of emits as reacted (engagement signal).

User-facing text PT, plain_text, chat_id from the config entry (notify.py).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime

from homeassistant.core import HomeAssistant, callback

from .agent_automations import (
    AgentAutomations,
    build_spec,
    describe_action,
    describe_trigger,
)
from .ai_client import AiTaskClient
from .config import PermearConfig
from .const import (
    CONDITION_LIST_MAX,
    CONVERSATION_RETRY_DELAYS,
    MONITORED_ENTITIES_RELATIVE_PATH,
    REACTION_WINDOW_MINUTES,
    SPEC_ENTITY_DOMAINS,
    TELEGRAM_CONFIRM_WORDS,
    TELEGRAM_DEDUP_TTL_SECONDS,
    TELEGRAM_REJECT_WORDS,
)
from .error_monitor import archive_error
from .household import (
    agent_preamble,
    describe_condition_pt,
    get_resident_names,
    memory_block,
    outbound_block,
)
from .notify import (
    async_answer_callback,
    async_edit_message,
    async_send_telegram,
    async_set_last_message,
    recent_outbound,
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
# v9.26 — the declared conditions have a permanent way out (R2), in the same
# shape as the standing rules: a list card with one Remover button each.
# v9.26b — any message that names "condição" with a verb of listing or of
# removing is routed here, before the conversation (which can only talk). A
# removal names "#id" or the card's own number; without one, the card answers.
# v9.26b — intents, not words: "não tenho condição", "condições do tempo" are
# ordinary Portuguese and go to the conversation. A list names "minhas/suas
# condições", a listing verb, "quais condições … guardou/tem/valem", or is
# just "condições?". A removal needs a removal verb and a stored condition: a
# determiner ("a/essa/aquela condição") or a number right after "condição".
_COND_PLURAL = r"condi(?:c|ç)(?:oes|ões)"
_COND_SINGULAR = r"condi(?:c|ç)(?:ao|ão)"
_CONDITION_LIST = re.compile(
    rf"\b(?:minhas|suas) {_COND_PLURAL}\b"
    rf"|\b(?:listar|liste|lista|listem|mostrar|mostra|mostre)\b.*\b{_COND_PLURAL}\b"
    rf"|\bquais\b.*\b{_COND_PLURAL}\b.*\b(?:guard\w*|tem|existem|valem|vigor|salv\w*)\b"
    rf"|\b{_COND_PLURAL} (?:guardadas|salvas|em vigor)\b"
    rf"|^\s*{_COND_PLURAL}\s*\??\s*$"
)
_CONDITION_REMOVE_VERB = re.compile(
    r"\b(?:remover|remova|remove|apagar|apague|apaga|excluir|exclua|exclui|"
    r"tirar|tira|tire|retirar|retire|esquecer|esquece|esque(?:c|ç)a|deletar|"
    r"delete|cancelar|cancele|cancela|desativar|desative|desativa)\b"
    r"|\bn(?:a|ã)o quero mais\b"
)
_CONDITION_TARGET = re.compile(
    rf"\b(?:a|as|essa|essas|esta|estas|aquela|aquelas) (?:{_COND_SINGULAR}|{_COND_PLURAL})\b"
    rf"|\b{_COND_SINGULAR}\s*(?:n(?:º|o|°|\.)\s*)?#?\s*\d+"
)
_CONDITION_ID = re.compile(rf"{_COND_SINGULAR}\s*#\s*(\d+)|#\s*(\d+)")
_CONDITION_NUMBER = re.compile(rf"\b{_COND_SINGULAR}\s*(?:n(?:º|o|°|\.)\s*)?(\d+)\b")
# v9.16 — an answer to a suggestion: a verb, optionally the #id it refers to.
_SUGGESTION_ANSWER = re.compile(
    r"^(sim|aceito|aceitar|aceita|nao|não|recuso|recusar|recusa)\b[^\d]*#?(\d+)?"
)
_OFFERED_ID = re.compile(r"#(\d+)")
_SUGGESTION_NAMED = re.compile(r"sugest[aã]o\b|automa[cç]")
_CONV_ERROR_MARKERS = ("Sorry, I had a problem", "503", "UNAVAILABLE")

SPEC_STRUCTURE = {
    "alias": {
        "description": "Nome curto do aviso em PT-BR. Vazio se o pedido nao for um aviso.",
        "required": True,
        "selector": {"text": {}},
    },
    "trigger_type": {
        "description": "Tipo do gatilho: time ou state",
        "required": True,
        "selector": {"select": {"options": ["time", "state"]}},
    },
    "trigger_config": {
        "description": 'JSON do gatilho. Ex: {"at":"18:00:00"} ou {"entity_id":"x","to":"on"}',
        "required": True,
        "selector": {"text": {}},
    },
    "action_message": {
        "description": "Texto do aviso ao morador.",
        "required": True,
        "selector": {"text": {}},
    },
    "condition_text": {
        "description": "Condicao em linguagem natural ou vazio",
        "required": False,
        "selector": {"text": {}},
    },
    "condition_config": {
        "description": 'JSON da condicao, ou vazio. Ex: {"condition":"state","entity_id":"x","state":"on"}',
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
        # v9.10 — timestamps of the system's own deliveries already shown to
        # the LIVE HA chat session; reset whenever that session is gone.
        self._outbound_seen: set = set()
        # v9.16 — when the conversation last spoke; anything the system offered
        # before that has been talked past.
        self._last_turn_at: datetime | None = None

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

        # v9.26b — after the standing-rule flows: "tira a condição" while a
        # proposal is being edited is about the proposal.
        if _CONDITION_REMOVE_VERB.search(lower) and _CONDITION_TARGET.search(lower):
            await self._condition_removal_turn(lower)
            return
        if _CONDITION_LIST.search(lower):
            await self._send_conditions_card()
            return

        if await self._suggestion_turn(lower):
            return

        await self._conversation_flow(text)

    # ------------------------------------------------------------------
    # Answering a suggestion (v9.16)
    # ------------------------------------------------------------------

    async def _suggestion_turn(self, lower: str) -> bool:
        """True when this message answered a suggestion. Nothing here chooses
        for the resident: 'aceito'/'recuso' or a #id are explicit; a bare
        sim/não only counts over what the system has just offered, because a
        week-long 'sim' would also catch the reply to any other question."""
        match = _SUGGESTION_ANSWER.match(lower)
        if not match:
            return False
        word, number = match.group(1), match.group(2)
        explicit = word not in ("sim", "nao", "não")
        pending = await self._storage.async_pending_suggestions()
        if number:
            target = [p for p in pending if p["id"] == int(number)]
            if not target:
                if not explicit:
                    return False
                await async_send_telegram(
                    self._hass, f"Nao ha sugestao #{number} pendente."
                )
                return True
        elif explicit:
            # A sentence that merely opens with the verb is not an answer.
            if lower != word and not _SUGGESTION_NAMED.search(lower):
                return False
            target = pending
            if not target:
                await async_send_telegram(
                    self._hass, "Nao ha sugestao pendente."
                )
                return True
        else:
            if lower not in TELEGRAM_CONFIRM_WORDS | TELEGRAM_REJECT_WORDS:
                return False
            offered = self._offered_ids()
            target = [p for p in pending if p["id"] in offered]
            if not target:
                return False
        if len(target) > 1:
            lines = [f"#{p['id']}: {p['content']}" for p in target]
            lines.append("Responda: aceito N ou recuso N.")
            await async_send_telegram(self._hass, "\n".join(lines))
            return True
        if word.startswith(("sim", "aceit")):
            await self._accept_suggestion(target[0])
        else:
            await self._storage.async_answer_suggestion(target[0]["id"], False)
            await async_send_telegram(
                self._hass, f"Sugestao #{target[0]['id']} recusada."
            )
        return True

    def _offered_ids(self) -> set:
        """The #ids in the system's last message, unless the conversation has
        spoken since. The ring is in memory: after a restart nothing is on
        offer, and a bare sim falls through to the conversation."""
        said = recent_outbound(self._hass)
        if not said:
            return set()
        last = said[-1]
        if self._last_turn_at and self._last_turn_at >= last["ts"]:
            return set()
        return {int(n) for n in _OFFERED_ID.findall(last["text"])}

    async def _accept_suggestion(self, suggestion: dict) -> None:
        """The yes is the authorization: build, write, answer in one line."""
        spec, error = await self._spec_from_text(suggestion["content"])
        if spec is None:
            await async_send_telegram(
                self._hass,
                f"Sugestao #{suggestion['id']} nao virou aviso: "
                f"{error or 'so sei avisar, nao aciono aparelhos'}.",
            )
            return
        result = await self._autos.async_create(spec)
        if result.startswith("Aviso criado"):
            await self._storage.async_answer_suggestion(suggestion["id"], True)
        await async_send_telegram(self._hass, result)

    # ------------------------------------------------------------------
    # Automation-spec creation (awaiting_* → ONE ai_task call)
    # ------------------------------------------------------------------

    async def _spec_creation_flow(self, text: str) -> None:
        is_edit = (
            self._pending_state == "awaiting_edit" and self._pending_spec is not None
        )
        spec, error = await self._spec_from_text(text, is_edit)
        if spec is None and not error:
            self._set_state("", None)
            await async_send_telegram(
                self._hass,
                "⚠️ Nao consegui interpretar a descricao.\n\n"
                'Tente reformular com mais detalhes, ex:\n'
                '"me avise as 18h se a porta estiver aberta"',
            )
            return

        if spec is None:
            # State stays awaiting — the user can rephrase and retry
            await async_send_telegram(
                self._hass,
                f"❌ Erro ao montar o aviso.\n\n{error[:200]}",
            )
            return

        self._set_state("pending", spec)
        await async_send_telegram(
            self._hass,
            "✨ Novo aviso\n\n"
            f"📌 {spec['alias']}\n\n"
            f"Quando: {describe_trigger(spec)}\n"
            f"O que faz: {describe_action(spec)}",
            inline_keyboard=[
                "Criar:/cnew_confirm, Ajustar:/cedt_request",
                "Descartar:/cdsc_clear",
            ],
        )

    async def _spec_from_text(
        self, text: str, is_edit: bool = False
    ) -> tuple[dict | None, str]:
        """Text → validated rule: (rule, ""), (None, reason), or (None, "") when
        the text is not something to be told. One ai_task call."""
        entities_text = await self._hass.async_add_executor_job(
            self._monitored_entities_text
        )
        data = await self._llm.async_generate(
            "HA automation creation",
            self._build_spec_prompt(text, entities_text, is_edit),
            SPEC_STRUCTURE,
        )
        if data is None:
            return None, "provedor indisponivel"
        if len(str(data.get("alias") or "").strip()) < 3:
            return None, ""
        return build_spec(data, consented_text=text)

    def _build_spec_prompt(self, text: str, entities_text: str, is_edit: bool) -> str:
        if is_edit:
            head = (
                f"Automacao existente (JSON): {json.dumps(self._pending_spec, ensure_ascii=False)}\n\n"
                f'O usuario quer modificar com: "{text}"\n'
                "Produza uma nova especificacao completa aplicando a modificacao solicitada."
            )
        else:
            head = f'Crie um aviso ao morador baseado na descricao:\n"{text}"'
        return f"""{head}

O aviso so fala: nunca aciona aparelho. Se a descricao pedir para ligar, desligar,
abrir, fechar ou ajustar algo, retorne alias vazio.

Regras:
- alias: nome curto em PT-BR, sem aspas especiais
- trigger_type e trigger_config:
  time: {{"at":"HH:MM:SS"}}
  state: {{"entity_id":"x","to":"estado"}}
- action_message: o texto do aviso. O estado de uma entidade entra so como {{{{ states('sensor.x') }}}}
- condition_text: condicao em linguagem natural ou deixe vazio
- condition_config: se houver condicao, o JSON dela, de um destes tipos:
  outra entidade em um estado: {{"condition":"state","entity_id":"x","state":"on"}}
  ninguem em casa: {{"condition":"presenca"}}
  o proprio estado mantido por N segundos (so com gatilho state): {{"condition":"duracao","min_seconds":N}}
  negacao de uma delas: {{"condition":"not","conditions":[{{"condition":"state","entity_id":"x","state":"y"}}]}}

Use SOMENTE estes entity_ids:
{entities_text}"""

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
        # v9.10 — HA drops a chat session after 5 idle minutes and reuses our
        # custom id with an EMPTY history. Whatever the dead session was told
        # is gone: the preamble, the memory block and the system's own
        # deliveries all go out again in the next session.
        if not self._chat_session_alive(conv_id):
            self._context_conv_id = None
            self._outbound_seen = set()
        # v9.9 — what Organic Memory has learned reaches the turn, with the
        # preamble: once per live chat session, never on every message.
        memory = ""
        if conv_id != self._context_conv_id:
            try:
                learned = await self._storage.async_conversation_memory()
                learned["conditions"] = [
                    {**c, "text": describe_condition_pt(c, self._friendly)}
                    for c in learned.get("conditions") or []
                ]
                memory = memory_block(
                    get_resident_names(self._hass),
                    self._config.primary_resident,
                    learned,
                )
            except Exception:  # noqa: BLE001 — memory must never block a reply
                _LOGGER.exception("Conversation memory block failed")
        # v9.10 — what the system said on its own since this chat session last
        # saw it.
        unseen = [
            m for m in recent_outbound(self._hass)
            if m["ts"] not in self._outbound_seen
        ]
        said = outbound_block(unseen)
        prompt = self._build_conversation_prompt(text, conv_id, memory, said)
        self._last_turn_at = datetime.now()

        speech = None
        if self._config.conversation:
            speech = await self._converse(self._config.conversation, prompt, conv_id)
        if speech is None and self._config.conversation_fallback:
            try:
                from homeassistant.components.conversation.chat_log import DATA_CHAT_LOGS
                chat_logs = self._hass.data.get(DATA_CHAT_LOGS)
                if chat_logs and conv_id in chat_logs:
                    chat_log = chat_logs[conv_id]
                    if chat_log.content and type(chat_log.content[-1]).__name__ == "UserContent":
                        _LOGGER.info("Cleaning up invalid conversation state (dangling UserContent) for ID %s before fallback", conv_id)
                        chat_log.content.pop()
            except Exception as e:
                _LOGGER.error("Failed to clean up chat log state: %s", e)

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
        # Preamble delivered for this chat session — don't repeat it.
        # (Only marked on success: a fully failed call re-injects next time.)
        self._context_conv_id = conv_id
        self._outbound_seen.update(m["ts"] for m in unseen)

        # Internal agent tokens — intercepted, never shown to the user
        if "REMOVE_AUTO:" in speech:
            ident = speech.split("REMOVE_AUTO:")[1].strip().split("\n")[0].strip()
            await async_send_telegram(self._hass, await self._autos.async_remove(ident))
            return
        if "LIST_AUTOS" in speech:
            await async_send_telegram(self._hass, await self._autos.async_list_text())
            return
        request = speech.split("CREATE_AUTO:")[1].strip() if "CREATE_AUTO:" in speech else ""
        if request:
            await self._spec_creation_flow(request.split("\n")[0].strip())
            return
        if speech in _INTERNAL_TOKENS or speech.startswith(("CREATE_AUTO:", "REMOVE_AUTO:")):
            await async_send_telegram(
                self._hass,
                "⚠️ Nao consegui responder agora. Tente em alguns instantes.",
            )
            return

        # The reply is already in HA's chat log — not remembered as outbound.
        if await async_send_telegram(self._hass, speech, remember=False):
            await async_set_last_message(self._hass, speech)

    def _chat_session_alive(self, conv_id: str) -> bool:
        """True while HA still holds this conversation's chat log (it drops a
        session after 5 idle minutes and reuses our custom id with an EMPTY
        history)."""
        try:
            from homeassistant.components.conversation.chat_log import DATA_CHAT_LOGS
        except ImportError:
            return False
        return conv_id in (self._hass.data.get(DATA_CHAT_LOGS) or {})

    def _build_conversation_prompt(
        self, text: str, conv_id: str, memory: str = "", said: str = ""
    ) -> str:
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
            if memory:
                parts.append(memory)
        if said:
            parts.append(said)
        if any(k in lower for k in _AUTO_REQUEST_KEYWORDS):
            parts.append(
                "[INSTRUCAO OBRIGATORIA: Responda APENAS com uma linha no "
                "formato exato abaixo, sem nenhum outro texto:\n"
                "Para criar: CREATE_AUTO: o que avisar e quando\n"
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
                    "Novo aviso\n\n"
                    "Descreva quando e o que devo te avisar.\n"
                    'Ex: "me avise as 18h se a porta estiver aberta"',
                )
                self._set_state("awaiting_new", None)
            elif command == "/listar_automacoes":
                await self._send_list_card()
            elif command == "/listar_condicoes":
                await self._send_conditions_card()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Telegram command handling failed")

    async def _send_list_card(self) -> None:
        listing = await self._autos.async_list()
        autos = listing["automations"][:10]
        if not autos:
            await async_send_telegram(
                self._hass,
                "🤖 Seus avisos\n\n"
                "Nenhum aviso criado ainda.\n"
                "Use /nova_automacao para criar um.",
            )
            return
        lines = [f"🤖 Seus avisos ({listing['count']})", ""]
        lines += [f"{i}. {a['alias']}" for i, a in enumerate(autos, 1)]
        lines += ["", "Toque em Remover N para excluir."]
        keyboard = [
            f"Remover {i}:/drmv_confirm_{a['id']}" for i, a in enumerate(autos, 1)
        ]
        await async_send_telegram(
            self._hass, "\n".join(lines), inline_keyboard=keyboard
        )

    # ------------------------------------------------------------------
    # Declared conditions (v9.26, R2): list and remove
    # ------------------------------------------------------------------

    def _friendly(self, entity_id: str) -> str:
        state = self._hass.states.get(entity_id)
        name = state.attributes.get("friendly_name") if state is not None else None
        if name:
            return str(name)
        return entity_id.split(".", 1)[-1].replace("_", " ")

    def describe_declared_condition(self, item: dict) -> str:
        return describe_condition_pt(item, self._friendly)

    async def _send_conditions_card(self, ask_which: bool = False) -> None:
        conditions = await self._storage.async_list_conditions()
        if not conditions:
            await async_send_telegram(
                self._hass,
                "🧭 Suas condições\n\n"
                "Nenhuma condição guardada.\n"
                "Elas nascem do que você me explica, como \"a porta só importa "
                "com o ar ligado\".",
            )
            return
        # Every condition is listed with its #id; the first CONDITION_LIST_MAX
        # also get a button. The numbers are the card's, the same ones
        # "remover condição N" accepts.
        lines = [f"🧭 Suas condições ({len(conditions)})", ""]
        if ask_which:
            lines = ["Qual delas? Toque em Remover N ou diga \"remover condição N\".", "", *lines]
        for i, item in enumerate(conditions, 1):
            since = str(item.get("first_seen") or "")[:10]
            since = f"{since[8:10]}/{since[5:7]}" if len(since) == 10 else "?"
            lines.append(
                f"{i}. {self.describe_declared_condition(item)}"
                f" (#{item['id']}, desde {since})"
            )
        lines += ["", "Valem até você mudar ou remover. Toque em Remover N para excluir."]
        keyboard = [
            f"Remover {i}:/crmv_confirm_{item['id']}"
            for i, item in enumerate(conditions[:CONDITION_LIST_MAX], 1)
        ]
        # The numbers of THIS card, for "remover condição N" until the next one:
        # a removal does not renumber what the resident is reading.
        self._condition_card_ids = [item["id"] for item in conditions]
        await async_send_telegram(
            self._hass, "\n".join(lines), inline_keyboard=keyboard
        )

    async def _condition_removal_turn(self, lower: str) -> None:
        """'#N' is an id. 'condição N' is the number on the LAST card shown
        (kept in memory; a restart forgets it). Anything else, or no card yet:
        the card, asking which one. Numbers elsewhere in the sentence ('a da
        TV de 2 min 30 s') are not read."""
        by_id = _CONDITION_ID.search(lower)
        target = None
        if by_id:
            target = int(by_id.group(1) or by_id.group(2))
        else:
            number = _CONDITION_NUMBER.search(lower)
            shown = getattr(self, "_condition_card_ids", None) or []
            if number is not None and 1 <= int(number.group(1)) <= len(shown):
                target = shown[int(number.group(1)) - 1]
        if target is None:
            await self._send_conditions_card(ask_which=True)
            return
        await async_send_telegram(self._hass, await self._remove_condition(target))

    async def _remove_condition(self, item_id: int) -> str:
        removed = await self._storage.async_remove_condition(item_id)
        if removed is None:
            return (f"Não achei a condição #{item_id} em vigor. "
                    "Use /listar_condicoes para ver as que existem.")
        return (f"Condição #{item_id} removida: "
                f"{self.describe_declared_condition(removed)}. "
                "Se você disser de novo, ela volta a valer a partir de amanhã.")

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

        elif "crmv_confirm_" in cb_data:
            try:
                item_id = int(cb_data.split("crmv_confirm_")[1])
            except ValueError:
                return
            result = await self._remove_condition(item_id)
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
