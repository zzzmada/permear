# PERMEAR — Provider Setup Guide

This guide shows how to configure each supported AI provider in Home Assistant
and what to put in `permear.yaml`.

After any provider change: edit **both** `permear.yaml` and `secrets.yaml`
(v8 dual-maintenance), then reload HA (Dev Tools → YAML → Reload All).

---

## Google AI (Gemini) — free tier available

**HA integration:** Google Generative AI Conversation

**Setup:**
1. Install via HACS or HA integrations page.
2. Enter your Google AI Studio API key.
3. HA creates two entities:
   - `conversation.google_ai_conversation` — for the `conversation` slot
   - `ai_task.google_ai_task` — for the `data` slot

**permear.yaml:**
```yaml
providers:
  conversation: conversation.google_ai_conversation
  data: ai_task.google_ai_task
  conversation_fallback: conversation.google_ai_conversation
  data_fallback: ai_task.google_ai_task
```

**Known limits:** free tier has a daily quota and rate limits. Gemini can
sometimes ignore formatting instructions in long conversation histories.
PERMEAR injects the current date in Telegram messages as a workaround
(conversation_id rotates daily).

---

## DeepSeek via HA native integration

**HA integration:** DeepSeek (native, added in recent HA versions)

**Setup:**
1. Add integration in HA → Settings → Integrations → Add → DeepSeek.
2. Enter your DeepSeek API key.
3. HA creates:
   - `conversation.deepseek_<model_name>` — conversation slot
   - `ai_task.deepseek_<model_name>` — data slot

**permear.yaml:**
```yaml
providers:
  conversation: conversation.deepseek_deepseek_v4_flash
  data: ai_task.deepseek_deepseek_v4_flash
```

**Recommended for:** data slot (no daily quota, fast, cost-effective).

---

## OpenAI — direct

**HA integration:** OpenAI Conversation

**Setup:**
1. Add integration in HA → Settings → Integrations → Add → OpenAI Conversation.
2. Enter your OpenAI API key.
3. Entities created: `conversation.openai_conversation`, `ai_task.openai_ai_task`
   (exact names may vary by HA version).

**permear.yaml:**
```yaml
providers:
  conversation: conversation.openai_conversation
  data: ai_task.openai_ai_task
```

---

## OpenRouter (any model via OpenAI-compatible API)

**HA integration:** OpenAI Conversation (configured with a custom base URL)

OpenRouter lets you use Gemini, DeepSeek, Claude, Mistral, etc. via a single
API key, using the OpenAI-compatible interface.

**Setup:**
1. Add integration: OpenAI Conversation.
2. Set base URL to `https://openrouter.ai/api/v1`.
3. API key: your OpenRouter key.
4. Model: any OpenRouter model slug (e.g., `deepseek/deepseek-chat-v3-0324`).

**permear.yaml:**
```yaml
providers:
  data: ai_task.openai_conversation   # or whatever entity_id HA assigned
```

---

## Anthropic (Claude)

**HA integration:** Anthropic Conversation (check HA integrations page for
current availability)

**permear.yaml:**
```yaml
providers:
  conversation: conversation.anthropic_conversation
  data: ai_task.anthropic_ai_task
```

**Note:** Claude models handle long conversation histories well and respect
formatting instructions reliably. Good choice for the conversation slot.

---

## Ollama (local, no internet dependency)

**HA integration:** Ollama Conversation

**Setup:**
1. Run Ollama locally or via a container accessible from HA.
2. Add HA integration pointing to your Ollama endpoint.

**Limitations with PERMEAR:**
- No fallback feasible if the local instance is down.
- Model quality affects ARAS gray-zone resolution and Sleep Consolidation
  memory extraction. Use a model with ≥ 7B parameters.
- The `data_fallback` should point to a cloud provider for resilience.

**permear.yaml:**
```yaml
providers:
  conversation: conversation.ollama_conversation
  data: ai_task.ollama_ai_task
  conversation_fallback: conversation.ollama_conversation   # same = retry
  data_fallback: ai_task.google_ai_task                    # cloud fallback
```

---

## Finding your entity_ids

After adding a provider integration in HA:

1. Go to Developer Tools → States.
2. Search for `conversation.` to find conversation entities.
3. Search for `ai_task.` to find AI Task entities.

The entity_id is what you put in `permear.yaml`.

---

## The PM's current configuration (Nabu)

```yaml
providers:
  conversation: conversation.google_ai_conversation         # Gemini (primary)
  data: ai_task.deepseek_deepseek_v4_flash                 # DeepSeek (primary data)
  conversation_fallback: conversation.deepseek_deepseek_v4_flash  # DeepSeek fallback
  data_fallback: ai_task.google_ai_task                    # Gemini fallback data
```

Voice assistant (ReSpeaker) uses `conversation.deepseek_deepseek_v4_flash`
separately — configured in HA UI under Voice Assistants. Voice has no PERMEAR
fallback by design (HA limitation; mitigated by choosing a provider with no
daily quota).
