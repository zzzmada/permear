# BYOK Setup — DeepSeek via OpenRouter

**BYOK** (Bring Your Own Key) routes your OpenRouter requests through your own DeepSeek API key, instead of OpenRouter's shared infrastructure.

## Why bother?

Without BYOK:
- You pay OpenRouter's rate ($0.14/M input, $0.28/M output for DeepSeek V4-Flash) — same as DeepSeek direct
- Shared rate limits with everyone else on OpenRouter (you hit 429 errors when DeepInfra throttles)
- ~$5 on OpenRouter funds maybe 3-6 months of typical PERMEAR usage

With BYOK:
- Same per-token price (no markup)
- **Your own** rate limit (much higher)
- Routes to DeepSeek's primary infrastructure
- OpenRouter charges $0 for BYOK (free up to 1M requests/month)
- $5 on DeepSeek lasts ~4 years at typical usage

## Setup

### 1. Create DeepSeek API key

1. Go to https://platform.deepseek.com
2. Sign up
3. Top up — minimum $5 (you can pay with credit card)
4. Settings → API keys → Create new key
5. Copy the key (starts with `sk-`)

### 2. Add to OpenRouter

1. Go to https://openrouter.ai/settings/integrations
2. Find **DeepSeek** in the list
3. Click → **Provider Keys** → **+ Add Key** in the **Prioritized** section
4. Paste your DeepSeek key
5. Toggle **"Always use for this provider"** to ON
6. Save

That's it. Within seconds, your `ai_task.generate_data` calls via `openrouter_deepseek_v3` will route through your BYOK.

### 3. Verify it's working

Developer Tools → Actions:

```yaml
service: ai_task.generate_data
data:
  task_name: "BYOK test"
  entity_id: ai_task.openrouter_deepseek_v3
  instructions: "Reply with the single word OK."
  structure:
    response:
      selector:
        text: {}
```

After 30 seconds:
- **OpenRouter Activity** (`openrouter.ai/activity`) should show the request at **$0.00** cost
- **DeepSeek Usage** (`platform.deepseek.com/usage`) should show 1 request, costing a few fractions of a cent

If OpenRouter shows non-zero cost and DeepSeek shows no activity, BYOK is **not** being used. Check:
- The key is in **Prioritized** (not Fallback)
- "Always use for this provider" toggle is ON
- The DeepSeek key is valid (test with curl below)

### Test DeepSeek key directly

```bash
curl -s https://api.deepseek.com/v1/chat/completions \
  -H "Authorization: Bearer YOUR_DEEPSEEK_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-chat",
    "messages": [{"role": "user", "content": "Say OK"}],
    "max_tokens": 10
  }'
```

Should return JSON with `choices[0].message.content` containing "OK". If you get 401/403, the key is invalid.

## Model version notes

OpenRouter's `deepseek/deepseek-chat` alias points to the **current generation** DeepSeek model. As of mid-2026, that's **V4-Flash** (replacing V3).

If your HA AI Task entity was configured with a specific older version (e.g. `deepseek/deepseek-chat-v3-0324`), you may want to migrate to `deepseek/deepseek-v4-flash` directly to avoid alias drift.

**V4-Flash highlights:**
- $0.14/M input, $0.28/M output (cache-miss)
- **$0.0028/M cached input** (98% off for repeated prefixes — PERMEAR benefits since briefings reuse soul.json/users.json structure)
- 1M token context window
- MIT-licensed open weights

## Expected costs

Typical PERMEAR household with all cycles active:

| Cycle | Monthly volume |
|---|---|
| Hourly pre-briefing × 12/day × 30 days | ~540K input + 36K output |
| Daily briefing memory extraction | ~60K input + 6K output |
| Weekly compile (3 calls × 4 weeks) | ~60K input + 6K output |
| Sporadic CREATE_AUTO, quick learning | ~25K input + 2.5K output |
| **Total** | **~685K input + 50K output** |

**Worst case (zero cache hits):** $0.11/month  
**Realistic (50% cache hit):** $0.06/month  
**With $5 on DeepSeek:** lasts 3-6 years.

The Gemini secondary stays in free tier (interactive Telegram + occasional fallback).

## Troubleshooting

### "Provider returned error 429"

Means your BYOK is **not** active (still using shared key). Re-check toggle and prioritization.

### "Invalid API key" from OpenRouter

Your DeepSeek key got revoked or has a typo. Re-paste it in OpenRouter.

### DeepSeek dashboard shows zero usage but calls work

Likely model alias mismatch. OpenRouter may be calling a model your DeepSeek account doesn't have BYOK-mapped to. In that case OpenRouter falls back to its shared infrastructure (and bills you). Check OpenRouter Activity — if cost > $0, BYOK was bypassed.

Solution: configure your HA AI Task entity with a specific model slug like `deepseek/deepseek-v4-flash` rather than the generic `deepseek-chat` alias.
