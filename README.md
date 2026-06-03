# PERMEAR

**A cognitive memory and salience layer for Home Assistant.**

PERMEAR filters by inhibition rather than broadcast. It observes household
events, consolidates what repeats, lets noise fade, and surfaces only what
warrants attention. It runs on a Raspberry Pi 4 with 2 GB of RAM.

---

## What it does

PERMEAR sits alongside your Home Assistant installation and watches what
happens. Most of what happens isn't worth telling you about — and PERMEAR
knows that.

When something does merit your attention, it sends a Telegram message. When
something doesn't, it stays quiet. The decision is made by a dedicated
filter (the ARAS Filter, named after the brain's attentional gating system)
that scores each candidate event on novelty, anomaly, priority, and
contextual match.

What earns attention is also remembered. Memory consolidates with
repetition, decays without it, and reorganizes itself nightly. Patterns
emerge from accumulation, not from LLM detection. The system gets
selective about familiar things and stays attentive to new or important
ones — without any seeding or initial configuration.

Automation in PERMEAR is a consequence of memory and attention, not the
product. The system observes long enough to suggest automation rules that
match what you actually do.

---

## How it works

```
household events
       │
       ▼
  event_buffer (SQLite, today only)
       │
       ▼
  Heartbeat (hourly, 08:30–20:00)
  build_candidates → ARAS Filter → emit / suppress / gray zone
       │                                      │
       │                                      ▼  (gray only)
       │                            ai_task call (data provider)
       │                                      │
       ▼                                      ▼
  Telegram (emit)                  Telegram (after LLM judgment)
       │
       ▼
  Organic Memory (memory_items, tiered SQLite)
       │
       ▼
  Sleep Consolidation (23:30)
  extract memories → write to DB → run tier maintenance → priority loop
       │
       ▼
  Systems Consolidation (Sundays 04:00)
  detect weekly patterns → action_items in guidelines.json
```

Five surfaces: Telegram messages, the SQLite memory DB, the
`sensor.permear_attention` (attention stats), the `sensor.permear_health`
(system status), and the `guidelines.json` file (your declared household
config, which the system reads but never edits).

---

## The ARAS Filter

The Ascending Reticular Activating System (ARAS) is the brain region that
decides which incoming sensory signals reach conscious attention. Its
defining mechanism is **inhibition**: most signals are suppressed; few are
let through. PERMEAR's filter does the same.

Each candidate event is scored on four axes:

| Axis | Range | Description |
|---|---|---|
| novelty | 0–2 | Compared by canonical key (`type:entity_id`), not raw text |
| anomaly | 0–1 | Deviation from observed baseline |
| priority | 0–2 | User-set or memory-learned weight |
| user_match | −2..0 | Penalty for events misaligned with current context |

The result determines what happens:

- **Score ≤ 1** → suppressed silently
- **Score ≥ dynamic threshold** → emitted directly to Telegram
- **In between** → one `ai_task` call resolves the gray zone

The emit threshold is **dynamic and relative to the entity park**:

```
threshold = MIN(2) + maturity × (MAX(4) − MIN(2))
maturity  = min((consolidated_items / exposed_entities) / 0.5, 1.0)
```

The system is born curious (threshold = 2, novelty alone is enough),
matures over weeks of observation, and becomes selectively attentive
(threshold = 4) once it has learned the house. The threshold scales for
any household size with no seeding.

Sensitivity is user-tunable in `permear.yaml`: `sensitive` / `balanced`
(default) / `quiet`.

---

## Organic Memory

Memory lives in SQLite (`memory/permear_memory.db`) with FTS5 for free-text
similarity. It is tiered — every memory item has a tier that changes based
on reinforcement and silence:

| Tier | Meaning | Transitions in |
|---|---|---|
| **ephemeral** | Just observed; may be forgotten | — |
| **active** | Repeated enough to matter | mention_count ≥ 3 within 30 days |
| **stable** | Persistent feature of the household | mention_count ≥ 10 within 90 days |
| **faded** | Inactive; not deleted, just dormant | silent > 7 days from ephemeral |

When an observation crosses ephemeral → active, its `kind` changes from
`observation` to `pattern`. **The repetition itself is the pattern.** No
LLM is involved.

Reinforcement happens in two layers:

1. **Canonical key match** — deterministic. Same event-type for same entity
   reinforces, regardless of text wording.
2. **FTS semantic fallback** — for free-text observations without a
   canonical key, an FTS5 score ≤ −5.0 triggers reinforcement.

The threshold (−5.0) was calibrated empirically; earlier values caused
false merges between distinct observations.

---

## The self-regulating circuit

```
born curious (threshold 2, novelty alone suffices)
  → learns the house (events become memory with correct canonical keys)
  → memory consolidates (repetition → pattern, no LLM)
  → consolidated entity raises its own priority (loop tiers → priority)
  → selective about the familiar, attentive to the new + the important
```

The circuit closes without seeding or configuration. Hierarchy of priority
sources: `user > learned > memory`. Human curation always wins over what
the system infers.

---

## AI provider architecture

PERMEAR uses four configurable provider slots, set in `permear.yaml`:

| Slot | Used for | Requires tools |
|---|---|---|
| `conversation` | Telegram, voice — controls devices | yes |
| `data` | Cycles (`ai_task`), judgment | no |
| `conversation_fallback` | Backup for conversation | yes |
| `data_fallback` | Backup for data | no |

If the primary conversation provider fails three times, the fallback
assumes — with tools intact, so the user doesn't notice the switch. If
both fail, the user gets an honest error: "Sistema temporariamente
indisponível."

There is no degraded mode. No "I'm operating in limited mode" responses.
This is a deliberate choice: a system that pretends to work when it isn't
is worse than one that admits the truth.

See `docs/providers.md` for setup with Gemini, DeepSeek (via OpenRouter),
OpenAI, Anthropic, Ollama, and others.

---

## Cycles

PERMEAR runs four scheduled cycles, all configurable in `permear.yaml`:

| Cycle | When | What it does |
|---|---|---|
| **Heartbeat** | Hourly, 08:30–20:00 | Reads `event_buffer`, runs ARAS, emits or suppresses |
| **Sleep Consolidation** | 23:30 | Extracts memories, writes them to DB, runs tier maintenance |
| **Systems Consolidation** | Sundays 04:00 | Weekly patterns become `action_items` in `guidelines.json` |
| **Wake** | 09:00 | Discovers new entities, sends a sensitive-new card if any |

Plus daily maintenance: reset flags at 00:00, cleanup at 00:05, housekeeping
on Sundays at 03:00. A continuous real-time error monitor runs outside the
ARAS pipeline (errors are not salience candidates by design).

---

## The two-layer contract

Different layers monitor different things:

| Layer | Scope |
|---|---|
| **Events** | Only entities with `monitor: true` generate `event_buffer` entries |
| **Health** | All entities monitored globally (battery, connectivity) |

This is intentional. Health monitoring stays global so that silent failures
on deprioritized entities are still detected. Event noise from those
entities is still filtered through ARAS.

---

## Voice channel (deliberate boundary)

PERMEAR does not decide when to speak through the voice channel
(ReSpeaker, satellite). The household author writes their own automations
that call `script.nabu_fala_respeaker` for specific events — a rain warning,
a window left open, whatever they want voiced.

The voice channel has no PERMEAR fallback. If the configured voice
provider is down, the script call fails silently. This is deliberate: voice
is a convenience channel, not a life-safety one, and adding fallback
complexity to it would add more failure modes than it prevents.

The system protects the resident from the system itself. Restraint and
silence are first-class features, not absence of capability.

---

## Why this exists

Most home assistants are designed to maximize interaction. The implicit
metric is engagement — how many things the system can tell you, suggest to
you, or ask you about. The result, in practice, is noise that buries the
few signals that actually matter.

I wanted the opposite. A home system that protects me from itself. One
where silence is the default and salience has to be earned. One where
memory works the way memory works — through repetition, decay, and slow
consolidation — rather than as a transcript that gets recalled by
keyword.

The design borrows from how the brain handles sensory input. The ARAS
doesn't broadcast; it inhibits. It decides what reaches awareness by
suppressing the rest. That model fit what I wanted to build, and the
vocabulary became the design map.

PERMEAR runs on a Raspberry Pi 4 with 2 GB of RAM. That isn't a limit I'm
working around — it's a constraint I designed for. If it doesn't fit
there, it doesn't belong.

---

## Configuration

`/config/permear.yaml` is the single file users edit. Four sections:

- **`providers:`** — the four AI provider slots
- **`agent:`** — primary resident identifier (used in cycle prompts)
- **`aras:`** — sensitivity level (`sensitive` / `balanced` / `quiet`)
- **`cycles:`** — Heartbeat window, Sleep time, Systems time

See `docs/configuration.md` for the full reference and
`docs/providers.md` for provider-specific setup. The conversation agent
system prompt template is in `docs/agent_prompt_template.md`.

---

## Installation (manual — HACS support planned for v10)

1. Copy this repository's contents to your HA `/config/` directory.
2. In `configuration.yaml`, add the two lines from `configuration_example.yaml`
   that load the PERMEAR package.
3. Edit `permear.yaml` with your AI providers and household resident name.
4. Edit `memory/guidelines.json` with your household residents.
5. Restart Home Assistant. The memory database initializes on startup.
6. PERMEAR begins observing immediately. The first Heartbeat runs within
   the hour.

Private files to add to `.gitignore` if you fork: `memory/permear_memory.db`,
`memory/guidelines.json`, `memory/monitored_entities.json`, `secrets.yaml`,
and any household-specific automation files.

---

## Status

Current release: **v8.2.0** (June 2026). Production-validated on a
Raspberry Pi 4 (2 GB) running Home Assistant OS. SQLite memory, dynamic
threshold, four-slot provider architecture, English codebase.

Next: v9 brings HACS installability (custom repository), an install
wizard, schema migrations, and minimal smoke tests. See `ROADMAP.md`.

---

## License

See `LICENSE`.
