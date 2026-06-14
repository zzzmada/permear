# PERMEAR

**A cognitive memory and salience layer for Home Assistant.**

PERMEAR filters by inhibition rather than broadcast. It watches household
events, consolidates what repeats, lets noise fade, and surfaces only what
warrants your attention. It is designed to run on hardware as small as a
Raspberry Pi 4 (2 GB).

It is not an assistant, an automation pack, or a copilot. It is an
attentional layer: most of what happens in a home is not worth a
notification, and PERMEAR is built around that fact. Silence is its default
state.

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

## Privacy notice — please read before installing

PERMEAR sends data to the Large Language Model (LLM) providers you
configure. Depending on your setup, those providers may be **cloud
services**. Specifically, the following can be sent to your configured LLM:

- **Event descriptions** during the gray-zone judgment and the nightly
  consolidation (e.g. which entities changed, when, and humanized state
  text such as a media title or a room name).
- **Media titles** captured from media players (e.g. what is playing).
- **Your chat messages** to the agent over Telegram, and the agent's
  replies.

The deterministic core of PERMEAR (capture, the ARAS filter, tier
maintenance, correlation) runs **entirely on your device** and sends
nothing externally. Only the ambiguous cases — the gray zone, the nightly
memory extraction, the weekly suggestion, and direct conversation — involve
an LLM call.

If you configure **local** LLM providers, no data leaves your network. If
you configure cloud providers (e.g. a hosted model), the data above is sent
to them under their terms. Choose your providers accordingly.

---

## Requirements

- **Home Assistant 2025.7 or newer.**
- A **conversation** provider and an **ai_task** provider configured in Home
  Assistant (e.g. any integration that exposes a `conversation.*` entity and
  one that exposes an `ai_task.*` entity). PERMEAR asks for four during
  setup: a primary and a fallback for each.
- The **Telegram** integration (`telegram_bot`) configured — it is the
  primary output surface. PERMEAR will warn you if it is missing.
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
       │                                   │
       │                                   ▼  (gray only)
       │                         one ai_task call (data provider)
       │                                   │
       ▼                                   ▼
  Telegram (emit)                Telegram (after LLM judgment)
       │
       ▼
  Organic Memory (tiered SQLite)
       │
       ▼
  Sleep Consolidation (nightly)
  extract memories → write to DB → tier maintenance → priority loop
       │
       ▼
  Systems Consolidation (weekly)
  detect recurring co-occurrences → suggest an automation
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
| anomaly | 0–1 | Deviation from the observed baseline |
| priority | 0–2 | User-set or memory-learned weight |
| user_match | −2..0 | Penalty for events the resident asked not to hear about |

- **Score ≤ 1** → suppressed silently
- **Score ≥ dynamic threshold** → emitted to Telegram
- **In between** → one `ai_task` call resolves the gray zone

The threshold is **dynamic and relative to your entity park**:

```
threshold = MIN + maturity × (MAX − MIN)
maturity  = min((consolidated_items / exposed_entities) / 0.5, 1.0)
```

The system is born curious (low threshold — novelty alone is enough),
matures over weeks of observation, and becomes selectively attentive once it
has learned the house. It scales to any household size with no seeding and
no day-one configuration. Sensitivity (`sensitive` / `balanced` / `quiet`)
is the only ARAS knob, set in the options.

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
reinforced rises; memory that goes unmentioned decays. Restrictions you
express in conversation ("stop telling me about X") are learned as memory
and gently lower the salience of those events — without silencing genuine
anomalies.

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

**Anytime (options):**

- ARAS sensitivity: `sensitive` / `balanced` / `quiet`.
- Primary resident (chosen from your `person.*` entities).
- Cycle times: Heartbeat window start/end, Sleep time, Systems time.
- Agent name (optional — defaults to a neutral name).
- Voice hook (optional — a script/service ID of your own that PERMEAR will
  call when you want a voice surface; PERMEAR never decides to speak on its
  own).

Residents and rooms are read directly from Home Assistant (the `person`
registry and the area registry) — you do not maintain a separate list.

---

## What PERMEAR will not do

- It will not talk to you unless something earns it.
- It will not declare automations; it suggests, and you decide.
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
