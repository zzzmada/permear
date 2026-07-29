# PERMEAR

**A cognitive memory and salience layer for Home Assistant.**

PERMEAR filters by inhibition rather than broadcast. It watches household
events, consolidates what repeats, lets noise fade, and surfaces only what
warrants your attention. It is designed to run on hardware as small as a
Raspberry Pi 4 (2 GB).

It is not an assistant, an automation pack, or a copilot. It is an
attentional layer: most of what happens in a home is not worth a
notification, and PERMEAR is built around that fact. Silence is its default
state — and, rarely, an event that is both genuinely unusual and actionable
receives active attention instead of a dry line. That is the **orienting
reflex**: the system contextualizes, asks once, and treats your silence as a
complete answer.

---

## Installation (HACS custom repository)

PERMEAR is installed as a **custom repository** in HACS.

1. In Home Assistant, open **HACS**.
2. Click the three-dot menu (top right) → **Custom repositories**.
3. Add the repository URL `https://github.com/zzzmada/permear` and choose
   the category **Integration**.
4. Find **PERMEAR** in the HACS list and click **Download**.
5. **Restart Home Assistant.**
6. Go to **Settings → Devices & Services → Add Integration**, search for
   **PERMEAR**, and follow the configuration flow.

> Full guide on custom repositories:
> https://www.hacs.xyz/docs/faq/custom_repositories/

There is **no YAML configuration**. Everything is configured through the UI
(config flow and options). PERMEAR does not use `secrets.yaml` or any
configuration file.

---

## Expose your entities to Assist (important)

The conversation agent can only see the devices **you expose to Assist**.
If an entity is not exposed, the agent cannot read its state — and language
models tend to guess plausibly instead of admitting blindness.

In **Settings → Voice assistants → Expose**, expose the entities you want
the agent to know about. Whatever you leave unexposed, the agent will
honestly say it cannot see (PERMEAR instructs it to), but it can only be
accurate about what it can reach.

---

## Where your data goes

PERMEAR sends data only to the LLM providers **you** configure in Home
Assistant — and only for the small fraction of cases that need a language
model. You choose those providers, so you control where the data goes.

- If you point PERMEAR at **local** providers (for example a model served by
  Ollama), nothing leaves your network.
- If you point it at **cloud** providers, then for the ambiguous cases the
  following can be sent to them: short event descriptions (which entities
  changed, when, humanized state text such as a room name), media titles from
  media players, and your chat messages to the agent.

The deterministic core — capture, the ARAS filter, tier maintenance,
correlation — runs **entirely on your device** and sends nothing externally.
A language model is only involved in the gray-zone judgment, the nightly
memory extraction, the weekly suggestion, and direct conversation. Everything
else is local arithmetic.

In short: the privacy profile is whatever your chosen providers are. Pick
local providers for a fully on-device setup, or cloud providers if you prefer
their quality — PERMEAR is agnostic to the choice.

---

## Requirements

- **Home Assistant 2025.7 or newer.**
- A **conversation** provider and an **ai_task** provider configured in Home
  Assistant (any integration that exposes a `conversation.*` entity and one
  that exposes an `ai_task.*` entity, cloud or local). PERMEAR asks for four
  during setup: a primary and a fallback for each.
- The **Telegram** integration (`telegram_bot`) configured — it is the
  primary output surface. PERMEAR will warn you if it is missing. See the
  Home Assistant docs to set it up:
  https://www.home-assistant.io/integrations/telegram_bot/
- Optionally, for the error monitor to see Home Assistant errors, enable
  event firing in your `configuration.yaml`:

  ```yaml
  system_log:
    fire_event: true
  ```

  PERMEAR will create a Repair notification if this is off.

---

## How it works

```
household events
       │
       ▼
  event_buffer (SQLite, today only)
       │
       ▼
  Heartbeat (hourly, within a configurable daytime window)
  build candidates → ARAS Filter → emit / suppress / gray zone
       │                │                  │
       │                │ (rare spike:     ▼  (gray only)
       │                │  unusual AND     one ai_task call (data provider)
       │                │  important)      │
       │                ▼                  │
       │        Orienting Reflex           │
       │        contextualize + ask once   │
       ▼                │                  ▼
  Telegram (emit)       ▼          Telegram (after LLM judgment)
       │           Telegram
       ▼
  Organic Memory (tiered SQLite)
       │
       ▼
  Sleep Consolidation (nightly; briefing delivered at 08:00)
  extract memories → write to DB → tier maintenance → priority loop
       │
       ▼
  Systems Consolidation (weekly)
  detect recurring co-occurrences → suggest an automation
  learn from engagement → adjust priorities
```

Everything runs **in-process** inside the integration. There are no shell
scripts, no `command_line` sensors, no external tokens, and no REST calls
back into Home Assistant.

---

## The ARAS Filter

The Ascending Reticular Activating System (ARAS) is the brain region that
gates which incoming signals reach conscious attention. Its defining
mechanism is **inhibition**: most signals are suppressed; few pass. PERMEAR's
filter does the same.

Each candidate event is scored on four axes:

| Axis | Range | Description |
|---|---|---|
| novelty | 0–2 | Compared by canonical key (`type:entity_id`), not raw text |
| anomaly | 0–1 | An event at an hour unusual *for that entity* — a device that routinely acts at night is not flagged for it (habituation applied to time) |
| priority | 0–2 | User-set, engagement-learned, or memory-derived weight |
| user_match | −2..0 | Penalty for events the resident asked not to hear about |

- **Score ≤ 1** → suppressed silently
- **Score ≥ dynamic threshold** → emitted to Telegram
- **In between** → one `ai_task` call resolves the gray zone

The threshold is **dynamic, relative to your entity park — and it breathes**:

```
threshold = MIN + maturity × (MAX − MIN)
maturity  = min((consolidated_items / exposed_entities) / 0.5, 1.0)
```

The system is born curious (low threshold — novelty alone is enough) and
matures over weeks of observation into selective attention. Habituation also
**recovers**: if weeks pass without a single direct emission, the threshold
relaxes gradually — and a single emission restores it at once. A stimulus
that stops being presented regains the power to draw attention, exactly as
in biological habituation. It scales to any household size with no seeding
and no day-one configuration. Sensitivity (`sensitive` / `balanced` /
`quiet`) is the only ARAS knob, set in the options.

Trivial state changes (a plain switch toggling, repeated room occupancy) do
not earn an attention boost on their own — they still consolidate as memory,
but they don't claim your attention unless they're genuinely anomalous or
you mark them as a priority yourself. Standing conditions (a low battery)
are not treated as a new fact each morning: the reminder re-emerges roughly
weekly while the condition lasts. And when someone has been home in the last
two hours, lights left on are not treated as "forgotten".

### The orienting reflex

When an event is both **unexpected for that entity** and **of high
importance**, PERMEAR does not just print a line — it contextualizes and
asks once, calmly, then returns to silence. It fires rarely by design (a few
times a week at most, never daily), adds no extra messages (it only changes
how one already-passing event is treated), asks at most one question, never
offers to act, and treats your silence as a complete answer. Salience is
decided deterministically; the language model only chooses the phrasing.

---

## Organic Memory

Memory lives in SQLite with FTS5 for free-text similarity. It is **tiered**:
each item moves between tiers based on reinforcement and silence.

| Tier | Meaning |
|---|---|
| ephemeral | Just observed; may be forgotten |
| active | Repeated enough to matter |
| stable | Consolidated over time |
| faded | Decayed from disuse |

Patterns emerge from **accumulation**, not from LLM detection. Memory that is
reinforced rises; memory that goes unmentioned decays — **in both
directions**: a faded memory that is mentioned again comes back as a fresh
entry, so decay is real decay, never a black hole. Your own words are never
merged away: resident speech is deduplicated only on exact repetition, so a
re-stated instruction always reaches the nightly consolidation verbatim.

Restrictions you express in conversation ("stop telling me about X") are
learned as memory and gently lower the salience of those events — without
silencing genuine anomalies. The weekly cycle also learns from
**engagement**: entities whose alerts you consistently ignore lose priority
on their own.

The database carries a schema version and migrates forward across updates,
so your accumulated memory is preserved when you upgrade.

---

## Configuration

All configuration is in the UI.

**On install (config flow):**

- Four LLM providers: conversation, data, conversation fallback, data
  fallback.
- Telegram chat ID (optional — leave blank to use the bot's first permitted
  chat).

**Anytime (options → Configure):**

- The four LLM providers and the chat ID — reconfigurable without
  reinstalling, so you can switch models or accounts from the UI.
- ARAS sensitivity: `sensitive` / `balanced` / `quiet`.
- Primary resident (chosen from your `person.*` entities).
- Cycle times: Heartbeat window start/end, Sleep time, Systems time.
- Agent name (optional — defaults to a neutral name).
- Voice hook (optional — a script/service ID of your own that PERMEAR will
  call when you want a voice surface; PERMEAR never decides to speak on its
  own).

Residents and rooms are read directly from Home Assistant (the `person`
registry and the area registry) — you do not maintain a separate list. The
conversation agent receives household context at runtime, including
behavioral grounding (answer from real state; act on what was just said;
be honest about how it learns), so you do not need to write a system prompt
for it.

The nightly briefing and the weekly summary are generated overnight but
**delivered at 08:00** — the cycles run when the day is done; the message
waits for a reasonable hour.

---

## Health

`sensor.permear_health` reflects the **current** state of the system: all
good, a recent provider fallback, or **reduced perception** — when most of
your monitored entities have been unreachable for hours (a dead Zigbee mesh,
a network outage), the sensor says so instead of reporting everything fine.
Being blind is graver than being on a fallback, and the system tells you.

---

## What PERMEAR will not do

- It will not talk to you unless something earns it — and it will not
  message you to say it has nothing to say.
- It will not act on your devices. Even the orienting reflex only brings the
  rare, relevant thing to your attention and leaves the decision with you.
- It will not declare automations; it suggests, and you decide. A suggestion
  you never answer retires on its own — silence is treated as an answer.
- It does not use embeddings, a vector database, or any always-on assistant
  loop.
- It does not depend on the cloud for its core logic — only the configured
  LLM calls leave the device, and only if your providers are remote.

---

## Status

PERMEAR is published as a custom repository. It is a working system run in a
real household, but it is young software: treat the memory database as
valuable but not irreplaceable, and report issues on the tracker.

## License

MIT. See `LICENSE`.
