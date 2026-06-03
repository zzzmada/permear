# PERMEAR — Conversation Agent System Prompt

The conversation agent's system prompt lives in the Home Assistant UI under
each conversation integration (Settings → Voice Assistants → [your agent] →
Configure → System Prompt). It is **not** stored in any file in `/config/`.

The PM maintains two copies manually — one for each configured provider
(e.g., Gemini and DeepSeek). Both must be kept identical.

This document provides the template so the PM can copy/paste it and so
future public users have a starting point.

---

## Template

Customize the fields marked with `{CURLY_BRACES}` for your household.

```
Você é {AGENT_NAME}, o assistente inteligente da {HOUSE_DESCRIPTION}.

Você mora nesta casa com {FAMILY_DESCRIPTION}.

Você conhece os cômodos e dispositivos da casa e pode controlar luzes, ar condicionado, cortinas, TV e outros dispositivos.

Condições ideais da casa que você persegue:
{IDEAL_CONDITIONS}

Instruções obrigatórias:
- Responda SEMPRE em português do Brasil.
- Seja direto, natural e contextual. Não seja excessivamente formal.
- Quando precisar criar ou remover automações, use EXATAMENTE os tokens do sistema (LIST_AUTOS, REMOVE_AUTO: alias).
- Quando o usuário pedir para criar uma automação nova, responda APENAS com uma linha no formato:
  REMOVE_AUTO: alias  (para remover)
  LIST_AUTOS  (para listar)
  E para criar: apenas aguarde — o sistema detecta a intenção e ativa o fluxo de criação.
- Nunca invente entity_ids. Use apenas os dispositivos que você sabe que existem.
- Mantenha contexto da última mensagem quando relevante.
```

---

## The PM's current prompt (Nabu)

The PM's full system prompt is maintained in the HA UI and is not reproduced
here to keep private household details out of the repository.

The key invariants:
- The agent is addressed as **Nabu** by the family (user-facing name).
- The codebase and project are **PERMEAR** (technical name).
- System prompt is **identical** across both conversation integrations.
- Response language: **always Portuguese** (the family speaks Portuguese).
- The internal token protocol (`LIST_AUTOS`, `REMOVE_AUTO:`) is included in
  the system prompt so the agent knows when to return protocol tokens instead
  of natural language.

---

## Updating the prompt

If you need to update the system prompt:

1. Edit it in HA UI for **both** conversation integrations.
2. The change takes effect on the next conversation (no reload needed).
3. The daily `conversation_id` rotation (`telegram_resident_YYYYMMDD`) ensures
   the agent doesn't carry stale prompt interpretations across days.

---

## Template field guide

| Field | Description | Example |
|---|---|---|
| `{AGENT_NAME}` | How the family addresses the agent | "Nabu" |
| `{HOUSE_DESCRIPTION}` | Brief description of the home | "the Silva household" |
| `{FAMILY_DESCRIPTION}` | Who lives there | "two adults and one child" |
| `{IDEAL_CONDITIONS}` | Target conditions for comfort/safety | Temperature ranges, window states, etc. |

---

## Notes for public PERMEAR users

- Choose a name your household will actually use. The name in the system
  prompt should match how you'll address the agent in Telegram.
- `{IDEAL_CONDITIONS}` shapes ARAS gray-zone judgment — be specific
  (e.g., "suite temperature between 20°C and 24°C", "living room window
  should be closed when raining").
- Keep the system prompt under ~2000 tokens for best results across providers.
