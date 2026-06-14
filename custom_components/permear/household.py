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
    """PT context block for the conversation agent (runtime injection).

    Injected once per daily conversation, INSIDE the same block as the
    user's turn — never as a fake user turn or a fabricated assistant turn,
    which would corrupt the HA chat-log alternation. Kept minimal: identity,
    residents, rooms, and what the agent can do.
    """
    residents = get_residents(hass)
    rooms = get_rooms(hass)
    nomes = ", ".join(r["name"] for r in residents)
    principal = config.primary_resident or (
        residents[0]["name"] if residents else ""
    )
    nome_agente = config.agent_name or DEFAULT_AGENT_NAME

    linhas = [
        "[CONTEXTO PERMEAR — instrucao de sistema, nao e fala do usuario:",
        f"Voce e {nome_agente}, a superficie de conversa do PERMEAR, a camada "
        "de memoria cognitiva e saliencia desta casa (Home Assistant). "
        "Responda em portugues do Brasil, curto e direto.",
    ]
    if nomes:
        linha = f"Moradores: {nomes}."
        if principal:
            linha += f" Morador principal: {principal}."
        linhas.append(linha)
    if rooms:
        linhas.append(f"Comodos da casa: {', '.join(rooms)}.")
    linhas.append(
        "Voce pode responder sobre a casa e gerenciar automacoes criadas "
        "pelo agente: para listar, responda exatamente LIST_AUTOS; para "
        "remover, responda exatamente REMOVE_AUTO: <nome>. Novas automacoes "
        "sao criadas pelo comando /nova_automacao no Telegram.]"
    )
    return "\n".join(linhas)
