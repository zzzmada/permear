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
from .const import DEFAULT_AGENT_NAME


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
