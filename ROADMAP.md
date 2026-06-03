# ROADMAP — PERMEAR

What's ahead. For what's done, see `CHANGELOG.md`.

---

## v8.x — incremental refinements (post v8.2)

Small optional improvements that may land between v8.2 and v9.0 based on
real production experience. Registered for tracking; not committed.

### Emerging `user_fact` memories

The `kind=user_fact` memory category exists in the schema but no code path
generates entries yet. Auto-editing of resident config was intentionally
abandoned in v8 (config is user-curated, not LLM-evolved). The right design:
facts about residents emerge from observation the same way patterns do.

Open question to answer before designing: where does the system observe
resident-specific facts, and what triggers promotion from `observation`
to `user_fact`?

### Systems Consolidation — cross-dimensional patterns

Currently, Systems Consolidation generates `action_items` from one weekly
LLM call. The original design also envisioned detecting cross-entity
correlations (e.g., "bedroom light on after 11pm correlates with office
light off within 2 minutes"). These require an LLM over 7 days of
consolidated memory. Lower priority than v9 — high value once memory has
matured for a household over months.

### Gray zone reads consolidated patterns

When the Heartbeat gray zone fires, the LLM prompt currently has no
knowledge of patterns the system has already consolidated. Injecting
"here are the patterns learned for this entity" would let the LLM
suppress redundant alerts more intelligently. Pairs naturally with
cross-dimensional patterns above.

### Final removal of `circuit_breaker.py`

The file is marked INACTIVE in the codebase but still has six live
`shell_command` entries pointing to it from a prior architecture. Removing
those entries cleanly, then deleting the file, is housekeeping deferred
from the v8 audit (which confirmed the dependencies but did not remove
them).

---

## v9 — HACS preparation

Goal: make PERMEAR installable via HACS as a custom repository. Users add
the GitHub URL to HACS; the install wizard handles the rest.

### Install wizard

A first-run experience that:

- Detects the user's HA environment (exposed entities, HA version)
- Creates `permear.yaml` from a template with sensible defaults
- Walks through configuring the four provider slots
- Initializes the SQLite database
- Guides system prompt setup for the configured conversation agent(s)
- Validates the install by running one Heartbeat cycle and reporting

### Schema migrations

A `schema_version` table is added to `permear_memory.db`. The init script
reads it and applies migrations as needed. Users who update PERMEAR must
never lose existing memory silently.

### Minimal smoke tests

Not full coverage — just the contract surface:

- ARAS Filter scores a canonical event correctly
- `add_or_reinforce` on the same canonical key reinforces, not duplicates
- Dynamic threshold formula returns expected values for given inputs
- `event_buffer` cleanup removes only previous-day rows
- `guidelines.json` round-trips through the loader

Goal: catch regressions during HACS-era refactors. Not 100% coverage —
the contract surface only.

### Remaining legacy strings cleanup

Several Portuguese strings remain in places that are cross-surface
contracts (changing them requires updating Lovelace cards and other
consumers atomically):

- `command_line` sensor friendly names ("Memoria Dia Atual", "Memoria
  Perene")
- `json_attributes` keys (`eventos`, `interacoes`, ...) on sensors

These are translated in v9 as part of the HACS publication pass.

### Onboarding documentation

A short `GETTING_STARTED.md` readable in five minutes by someone who uses
Home Assistant but knows nothing about PERMEAR. Separate from the
technical `docs/`.

---

## v10 — HACS official listing

Goal: appear in the official HACS default repositories. Stable enough for
unattended use by users who never read source code.

### Custom component rewrite

Move from `shell_command` bridges to a proper `custom_components/permear`
integration. Python scripts become HA services. This eliminates the
`shell_command` layer entirely and makes PERMEAR installable with one
click.

### GUI for `permear.yaml`

A HA config flow or Lovelace panel for editing `permear.yaml` without
touching files. Validates inputs, shows current state of each section.

### Bilingual documentation

English + Portuguese user-facing docs. Code stays English.

### Long pause + real-user feedback

After v10, the project sits and gets used. New features wait for real
production pain from real users — not speculation.

---

## Rejected — the refusal list

These were explicitly considered and rejected. They are part of the
project's identity. Resist re-opening them without concrete new evidence.

### Vector DB / embeddings / hybrid retrieval

FTS5 covers household scale on RPi4 2 GB. Reconsider only when there is
concrete pain that FTS5 cannot solve. Never on speculation, never because
another project uses it.

### Auto-evolution of configuration by LLM

Config is user-curated. The system observes patterns in `memory_items`
without touching declared config in `guidelines.json`. Config files do
not decay — they are read, never written by the system.

### Auto-evolution of agent behavioral rules (the "soul" experiment)

Tried in v7 and abandoned in v8. Auto-rewriting of behavioral rules /
operating constraints produced nothing useful and conflicted with user
intent. Agent identity lives in the system prompt, curated manually.

The terminology matters: what was called "soul" was behavioral rules and
operating constraints, not personality or roleplay. The mechanism was
wrong for that — these are user-declared and should stay so.

### LLM-regulated ARAS threshold

The threshold is arithmetic (ratio of consolidated to exposed entities,
clamped). Keeping it deterministic is an explicit design value:
`lib/aras_filter.py` stays pure and testable.

### Degraded mode for conversation fallback (Reading 1)

If both conversation providers fail, the user receives an honest error
("Sistema temporariamente indisponível"). No degraded mode. No "I'm
operating in limited mode" responses. The dishonesty of pretending to
work was the problem we deliberately eliminated.

### Full unit test suite before v9

Tests on a fast-moving codebase become maintenance burden before they
add safety. Minimal smoke tests arrive in v9 when the surface stabilizes.
Reconsider full coverage only when the project matures.

### Custom web UI

Lovelace + Telegram + voice cover the user surface. A custom web app is
maintenance, hosting, and security overhead with no proportional value.

### Continuous-weight memory

The tier system (ephemeral / active / stable / faded) is more
interpretable and operationally sufficient. Tiers transition based on
counted events — debuggable, inspectable, aligned with biological
semantics.

### Formal multi-provider abstraction layer

`permear.yaml` providers + HA's `ai_task` and `conversation` integrations
already handle provider agnosticism at the level that matters. Building
an additional abstraction in PERMEAR's code would duplicate what HA does
natively.

### Voice channel as a PERMEAR-internal output

The voice channel (ReSpeaker, satellite) is deliberately external to
PERMEAR. The household author writes voice automations directly with
`script.nabu_fala_respeaker`. PERMEAR does not decide when to speak.
Voice is a convenience channel, not a salience-routing one.

### Inline-keyboard buttons for system actions

Buttons were a source of bugs (truncation, callback issues) and they
don't gain anything over the conversation flow that LLMs already handle
well ("are you sure?" / "yes"). Conversational confirmation is the right
pattern for actions the agent can mediate naturally.

---

## Design principles (compass for roadmap decisions)

When in doubt about whether to add something:

1. **Anti-overengineering.** Simple, functional, HA-native first.
2. **Single source of truth.** Don't duplicate state.
3. **RPi4 2 GB is a product boundary.** Not a temporary constraint.
4. **Silence is the default state.** Salience is earned, not broadcast.
5. **Memory is biological, not a log.** Tiered, reinforcement-based;
   patterns emerge from repetition, not from LLM detection.
6. **Don't build on speculation.** Features earn their place through real
   pain in production.
7. **Provider discipline.** Non-interactive judgment → `ai_task`;
   device-controlling conversation → `conversation`.
8. **Self-regulation over configuration.** The system works day-one with
   zero seeding and adapts to the household.
9. **Honest about state.** No degraded mode. No agent pretending to be
   something it isn't.
10. **The system protects the resident from the system itself.**
    Restraint, suppression, and silence are first-class features.
