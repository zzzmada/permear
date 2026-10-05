"""Household context from Home Assistant — single source of truth (v9.0.1).

Replaces guidelines.json: residents come from the person entities the user
already maintains in HA; rooms come from the area registry. Nothing is read
from or written to files — states and registries are in-memory and read on
the event loop (call these helpers from the loop, not from an executor).

Also builds the runtime conversation preamble, so the agent no longer
depends on a PERMEAR prompt hand-pasted into the HA agent UI.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import area_registry as ar

from .config import PermearConfig
from .const import CONVERSATION_MEMORY_MAX_CHARS, DEFAULT_AGENT_NAME


@callback
def get_residents(hass: HomeAssistant) -> list[dict]:
    """person.* entities → [{name, entity_id, home?}], sorted by name."""
    residents = []
    for state in hass.states.async_all("person"):
        name = (
            state.attributes.get("friendly_name")
            or state.entity_id.split(".", 1)[1].replace("_", " ")
        )
        entry: dict = {"name": name, "entity_id": state.entity_id}
        if state.state in ("home", "not_home"):
            entry["home"] = state.state == "home"
        residents.append(entry)
    residents.sort(key=lambda r: str(r["name"]).lower())
    return residents


@callback
def get_resident_names(hass: HomeAssistant) -> list[str]:
    return [r["name"] for r in get_residents(hass)]


@callback
def get_rooms(hass: HomeAssistant) -> list[str]:
    """Area registry names, sorted. Empty list when no areas are set up."""
    registry = ar.async_get(hass)
    return sorted(
        (area.name for area in registry.async_list_areas()), key=str.lower
    )


@callback
def agent_preamble(hass: HomeAssistant, config: PermearConfig) -> str:
    """PT context block for the conversation agent (runtime injection, v9.3).

    Injected once per daily conversation, INSIDE the same block as the
    user's turn — never as a fake user turn or a fabricated assistant turn,
    which would corrupt the HA chat-log alternation.

    Deliberately does NOT enumerate residents/rooms: that — with live states
    — already arrives via the Assist Live Context (llm_hass_api ["assist"]).
    Duplicating it competed with that context. The preamble POINTS to it and
    injects only universal behavior (real-state grounding, conversational
    context, how the agent learns) so the right conduct ships zero-config,
    independent of any prompt hand-pasted in the HA agent UI.
    """
    nome_agente = config.agent_name or DEFAULT_AGENT_NAME

    linhas = [
        "[CONTEXTO PERMEAR — instrucao de sistema, nao e fala do usuario:",
        f"Voce e {nome_agente}, a superficie de conversa do PERMEAR, a camada "
        "de memoria e atencao desta casa. O estado atual da casa — moradores "
        "presentes, comodos e dispositivos com seus estados — esta no contexto "
        "do sistema que acompanha esta conversa. Use SEMPRE esse estado real "
        "para responder; nunca presuma o que nao esta la. Se algo nao aparece, "
        "diga que nao consegue ver, em vez de adivinhar.",
        "Interprete cada mensagem no contexto do que voce acabou de dizer: se "
        "o morador responde curto ('desligue', 'sim', 'pode') logo apos uma "
        "observacao ou pergunta sua, aja sobre o que voce mesmo mencionou — "
        "nao pergunte 'o que?' nem repita uma confirmacao ja dada.",
        "Voce aprende observando o que se repete, nao gravando ordens. Se "
        "pedirem para lembrar ou associar algo, responda com honestidade "
        "('vou prestar atencao a isso') — sem afirmar que criou uma regra. "
        "Nunca mande o morador usar comandos tecnicos; isso nao e trabalho dele.",
        "Fale curto, direto, em portugues. Diga o necessario e pare.]",
    ]
    return "\n".join(linhas)


def _day_month(iso: str) -> str:
    """'2026-09-17T23:31:33' -> '17/09' (empty when malformed)."""
    return f"{iso[8:10]}/{iso[5:7]}" if len(iso) >= 10 else ""


def memory_block(
    resident_names: list[str], speaker: str | None, memory: dict
) -> str:
    """PT block with what Organic Memory has learned, for the conversation
    turn (v9.9). Pure: the caller reads the registries and the DB.

    Goes next to the preamble, once per daily conversation — the agent could
    not answer "quem mora aqui?" or "quais sao minhas preferencias?" because
    nothing the memory held ever reached the turn. Three things enter, each
    with its provenance: who lives here (names only; presence stays with the
    live context), the requests for silence still in force (dated), and the
    routines consolidated by repetition (counted and dated, flagged as past
    exemplars so their clock times are never narrated as today).

    Returns "" when there is nothing to say — day 1 stays untouched. Lines are
    dropped from the end rather than exceed CONVERSATION_MEMORY_MAX_CHARS.
    """
    linhas: list[str] = []
    if resident_names:
        quem = f"Moradores cadastrados: {', '.join(resident_names)}."
        if speaker:
            quem += f" Quem fala com voce: {speaker}."
        linhas.append(quem)
    rules = memory.get("rules") or []
    if rules:
        linhas.append("Preferencias ditas pelo morador, ainda em vigor:")
        for r in rules:
            quando = _day_month(str(r.get("last_seen") or ""))
            tipo = (
                "sugestao recusada" if r.get("scope") == "suggestion"
                else "pediu silencio"
            )
            linhas.append(f"- {r['content']} ({tipo}, dito em {quando})")
    routines = memory.get("routines") or []
    if routines:
        linhas.append(
            "Rotinas que se consolidaram por repeticao (cada linha e UM exemplo "
            "de um dia passado, nao um fato de hoje):"
        )
        for r in routines:
            desde = _day_month(str(r.get("first_seen") or ""))
            linhas.append(
                f"- {r['content']} (visto {r.get('mention_count', 1)}x "
                f"desde {desde})"
            )
    if not linhas:
        return ""
    cabecalho = (
        "[MEMORIA PERMEAR — o que esta casa ja ensinou; NAO e o estado atual, "
        "instrucao de sistema, nao e fala do usuario:"
    )
    rodape = (
        "Use isto so quando perguntarem sobre preferencias, rotina ou quem "
        "mora aqui; nao recite sem ser perguntado. Os horarios acima sao de "
        "dias passados: para o que acontece AGORA vale apenas o estado real. "
        "Se a resposta nao estiver aqui, diga que ainda nao aprendeu.]"
    )
    budget = CONVERSATION_MEMORY_MAX_CHARS - len(cabecalho) - len(rodape) - 2
    corpo: list[str] = []
    for linha in linhas:
        if len(linha) + 1 > budget:
            break
        corpo.append(linha)
        budget -= len(linha) + 1
    return "\n".join([cabecalho, *corpo, rodape])
