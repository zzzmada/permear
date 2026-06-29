"""Constants for the PERMEAR integration."""

DOMAIN = "permear"

# Config entry keys (v9.0 — config entry is the ONLY config source; the old
# /config/permear.yaml is abandoned and never read).
# data (config_flow, install time):
CONF_CONVERSATION = "conversation"
CONF_DATA = "data"
CONF_CONVERSATION_FALLBACK = "conversation_fallback"
CONF_DATA_FALLBACK = "data_fallback"
CONF_CHAT_ID = "telegram_chat_id"
# options (options_flow, adjustable without reinstall):
CONF_SENSITIVITY = "sensitivity"
CONF_PRIMARY_RESIDENT = "primary_resident"
CONF_HEARTBEAT_START = "heartbeat_start"
CONF_HEARTBEAT_END = "heartbeat_end"
CONF_SLEEP_TIME = "sleep_time"
CONF_SYSTEMS_TIME = "systems_time"
CONF_AGENT_NAME = "agent_name"
CONF_VOICE_SCRIPT = "voice_script"

DEFAULT_CHAT_ID = ""  # empty → telegram_bot uses the first allowed chat
# Neutral agent name used when agent_name is left empty — keeps the component
# brand-agnostic for public release (the agent's name is configurable, never
# hardcoded).
DEFAULT_AGENT_NAME = "PERMEAR"

# Paths relative to the HA config dir (resolve via hass.config.path()).
# guidelines.json is GONE (v9.0.1) — residents come from the HA person
# registry via household.py; the component never reads or writes that file.
# Organic Memory schema version — the version the schema in storage.py SCHEMA
# currently represents. The DB stamps it into PRAGMA user_version; storage._init
# reads that on open and applies any pending migrations up to here. Bump this
# (and register a migration) only when the logical schema changes — see the
# migration registry in storage.py.
SCHEMA_VERSION = 1

DB_RELATIVE_PATH = "memory/permear_memory.db"
MONITORED_ENTITIES_RELATIVE_PATH = "memory/monitored_entities.json"
AVAILABILITY_RELATIVE_PATH = "memory/availability_snapshot.json"
ARAS_STATS_RELATIVE_PATH = "memory/aras_stats.json"
AGENT_CIRCUIT_RELATIVE_PATH = "memory/agent_circuit.json"
ARCHIVED_ERRORS_RELATIVE_PATH = "memory/archived_errors.json"
# Append-only daily ARAS rollup (v9.2) — the series aras_stats.json (overwritten
# per day) cannot keep. One line per COMPLETED day; lets the PM validate spike
# rarity over weeks. Never a table — a light JSONL, flock-free (single writer).
ARAS_STATS_HISTORY_RELATIVE_PATH = "memory/aras_stats_history.jsonl"

# Capture contract (v8.8) — fixed, closed lists. Not user-configurable.
COVER_DEBOUNCE_SECONDS = 3.0

# RODADA H — media_player flaps (webOS device on->off in seconds) must not enter
# the buffer. A genuine TV/cast session lasts minutes, so a sub-window on->off is
# a flap. 10s mirrors OCCUPANCY_DEBOUNCE_SECONDS. NB: this only catches fast
# flickers; a longer flap (e.g. 81s) is caught by the Heartbeat's current-state
# check (REVERTIBLE_STATE_DOMAINS), not here — do not raise this to "cover" a
# long flap, it would blind short real use.
MEDIA_PLAYER_DEBOUNCE_SECONDS = 10.0

# RODADA H — domains whose state PERSISTS (an 'on' stays on until something turns
# it off). For these, a buffered event whose captured state no longer matches the
# entity's CURRENT state has reverted inside the 90-min window and is no longer
# news — the Heartbeat suppresses it. Deliberately EXCLUDES binary_sensor and
# vacuum: motion/door/etc. are pulse-like (the event is the pulse; "now off" is
# normal and expected), so they must not be blinded by a current-state check.
REVERTIBLE_STATE_DOMAINS = frozenset({
    "media_player", "switch", "light", "climate", "cover", "lock", "fan",
})

# Occupancy/motion/presence binary_sensors flood the event_log with on/off
# toggles and fake co-occurrence pairs. Instead of recording every toggle, the
# capture records ONE event when occupancy CLEARS, carrying how long it lasted
# (occupied_for_s, from the state's last_changed). An occupancy that held for
# less than OCCUPANCY_DEBOUNCE_S is treated as a transient pass-through (someone
# walking past a motion sensor) and dropped. The 'on' (becoming occupied) toggle
# is never written on its own — the sustained span is the event. This keeps the
# entity monitored (occupancy over time is valid data) without the noise.
PRESENCE_DEVICE_CLASSES = frozenset({"occupancy", "motion", "presence"})
OCCUPANCY_DEBOUNCE_SECONDS = 10.0

# Entity IDs that must never be recorded (safety net, mirrors record_event.py).
INVALID_ENTITY_IDS = frozenset({"", "-", "while", "mesmo", "None", "null"})

# States that are health signals, not household events (rule: events=exposed,
# health=global — availability is monitored elsewhere, never via the buffer).
IGNORED_STATES = frozenset({"unknown", "unavailable"})

# Domains that produce "household events" — discrete, user-actionable state
# changes. Excluded: sensor (numeric/continuous), weather, script, automation,
# input_*, number, and any domain not in this list.
CAPTURE_DOMAINS = frozenset({
    "cover", "media_player", "light", "climate",
    "binary_sensor", "lock", "switch", "fan", "vacuum",
})

# Domains whose emit is a bare on/off state with no informative metadata.
# RODADA B: these consolidate as memory normally (Sleep/Systems/correlation)
# but do NOT earn the tiers->priority boost — that +1 is exactly what pushes a
# dry switch (novelty 2 + 1 = threshold 3) to claim emission on its own. light
# is conditional: a dimmer (brightness ever recorded) is informative and KEEPS
# the boost; a relay light (never any brightness) is dry. Rich domains
# (climate/cover/media_player) and user/learned priority are never affected.
DRY_BOOST_EXCLUDED_DOMAINS = frozenset({"switch"})

# RODADA C: binary_sensor is heterogeneous. Noise classes (occupancy/motion/
# presence) toggle continuously and consolidate the same way switches did —
# they must NOT earn the boost (occupancy duration is already handled in
# v9.0.3; emitting the bare toggle is redundant). Signal classes (door,
# window, smoke, gas, moisture, safety...) and binary_sensors with NO
# device_class KEEP the boost — they are attention events. Deliberately the
# 3 noise classes only; when in doubt, keep the boost (don't blind a sensor).
NOISE_BINARY_DEVICE_CLASSES = frozenset({"occupancy", "motion", "presence"})

# Per-domain metadata contract: source attribute name -> metadata key.
# Closed list — deliberately NOT "everything HA exposes".
METADATA_ATTRIBUTES = {
    "cover": {"current_position": "position"},
    "media_player": {"media_title": "title"},
    "light": {"brightness": "brightness"},
    "climate": {"current_temperature": "temp", "temperature": "setpoint"},
}

# =============================================================================
# v8.9 — Heartbeat + ARAS (ported from scripts/permear_config.py)
# =============================================================================

# ARAS thresholds derive from permear.yaml aras.sensitivity — the ONLY knob
# exposed to users. The emit threshold is dynamic (computed per Heartbeat);
# it self-regulates and must never be tuned by hand.
SENSITIVITY_MAP = {
    "sensitive": (1, 3),  # more alerts, less filtering
    "balanced": (2, 4),   # production-calibrated default
    "quiet": (3, 5),      # fewer alerts, more selective
}
DEFAULT_SENSITIVITY = "balanced"

# Fixed calibration — not exposed to the user.
ARAS_MATURITY_FULL_RATIO = 0.5
ARAS_MATURITY_MIN_ENTITIES = 5
ARAS_SUPPRESS_THRESHOLD = 1

# Orienting reflex (v9.2 — the spike path). A spike RECLASSIFIES an event that
# would ALREADY emit — it never adds volume. An emit candidate whose ARAS axes
# show anomaly (broke the expected pattern) AND high priority is the "unexpected
# AND relevant": it gets active attention (the LLM contextualizes + asks ONCE)
# instead of a dry line. Rare by construction — priority>=2 is the TOP of the
# 0-2 scale (today only the 2 most consolidated entities reach it) and
# anomaly>=1 is the off-pattern signal. If it ever fires daily, the bar is wrong
# and rises. Determinism owns salience; the LLM owns only language. Design
# constants — never exposed in the UI (like the heartbeat interval).
SPIKE_MIN_PRIORITY = 2
SPIKE_MIN_ANOMALY = 1

# Nocturnal habituation (v9.2.2) — the circadian anomaly (event 0-6h → +1) is
# narrowed by the SAME habituation that already governs salience: an entity that
# REGULARLY acts at night is not anomalous at night FOR ITSELF. Deterministic,
# one query over the existing event_log — NOT the vetoed statistical baseline
# (no buckets, no share, no per-entity maturity, no new table). An entity counts
# as habitually nocturnal when it has events in the small hours on at least
# MIN_DAYS distinct days within the lookback (the "≥3 distinct days" mirrors the
# co-occurrence rule). Below that — or with no history (a new entity) — night
# stays anomalous (conservative: the unproven night event still earns a look).
NOCTURNAL_HABIT_MIN_DAYS = 3
NOCTURNAL_LOOKBACK_DAYS = 30

HEARTBEAT_WINDOW_MINUTES = 90
HEARTBEAT_INTERVAL_MINUTES = 60
HEARTBEAT_JITTER_SECONDS = (60, 300)
DEFAULT_HEARTBEAT_START = "08:30"
DEFAULT_HEARTBEAT_END = "20:00"
DEFAULT_SLEEP_TIME = "23:30"
DEFAULT_SYSTEMS_TIME = "04:00"

# Organic Memory — FTS similarity threshold for "same memory"
# (bm25: more negative = more similar; -5.0 avoids false merges, rule #35).
MEMORY_FTS_MIN_SCORE = -5.0

# Interoception — battery and connectivity signals.
BATTERY_THRESHOLD = 20
BATTERY_ENTITY_PATTERNS = ("_battery", "_battery_level")
BATTERY_DEVICE_CLASSES = ("battery",)
SILENT_STATES = ("unavailable", "unknown")
SILENT_IGNORE_DOMAINS = (
    "device_tracker", "person",   # presence, flicker constantly
    "automation", "script",       # unknown/unavailable is structural
    "button",                     # always unknown until pressed
    "stt", "tts", "notify",       # integration state, not hardware
    "update",                     # managed separately
)

# Window after a logged fallback during which the primary data provider is
# skipped (mirrors the 1h template guard in cycles.yaml).
FALLBACK_SKIP_PRIMARY_SECONDS = 3600

# RODADA D: sensor.permear_health reads CURRENT state, not "any fallback today".
# A fallback logged within this window means we are still running on the
# secondary; past it, the primary is assumed back and the state returns to
# tudo_ok. fallbacks_hoje stays as a daily-history attribute only.
HEALTH_FALLBACK_WINDOW_MINUTES = 20

# =============================================================================
# v8.10 — Sleep + Systems + Wake (ported from scripts/permear_config.py)
# =============================================================================

AGENT_AUTOMATIONS_RELATIVE_PATH = "automations/permear_agent.yaml"

# User-facing PT day names — index matches datetime.weekday() (Monday=0).
DAYS_PT = (
    "Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
    "Sexta-feira", "Sábado", "Domingo",
)

# Organic Memory tier transitions — fixed calibration, never user-tunable.
MEMORY_EPHEMERAL_FADE_DAYS = 7        # ephemeral without mention -> fade
MEMORY_ACTIVE_PROMOTE_MENTIONS = 3    # mentions for ephemeral -> active
MEMORY_ACTIVE_PROMOTE_WINDOW = 30     # window (days)
MEMORY_STABLE_PROMOTE_MENTIONS = 10   # mentions for active -> stable
MEMORY_STABLE_PROMOTE_WINDOW = 90     # window (days)
MEMORY_ACTIVE_DEMOTE_DAYS = 30        # active without mention -> ephemeral
MEMORY_STABLE_DEMOTE_DAYS = 90        # stable without mention -> active

# Engagement-based priority learning (weekly, Systems Consolidation).
ENGAGEMENT_MIN_ALERTS = 4       # minimum alerts to have confidence
ENGAGEMENT_UP_RATE = 0.66       # reaction rate >= raises priority
ENGAGEMENT_DOWN_RATE = 0.33     # reaction rate <= lowers priority

# Co-occurrence detection (v8.6 contract — deterministic, no LLM).
COOCCURRENCE_WINDOW_SECONDS = 120
COOCCURRENCE_MIN_DISTINCT_DAYS = 3   # distinct DAYS, never total count
EVENT_LOG_CORRELATION_DAYS = 7

# Daily DB cleanup (ports the shell maintenance chain — buffer 00:05,
# event_log 30d retention, daily_ flags reset).
DAILY_CLEANUP_TIME = "00:05"
EVENT_LOG_RETENTION_DAYS = 30

# Deferred cycle messages (v9.2.2) — Sleep (~23:30) and Systems (weekly) keep
# running at their times, but their Telegram message is PERSISTED here and only
# delivered at DEFERRED_SEND_HOUR:DEFERRED_SEND_MINUTE the next morning. A JSON
# file (not an in-memory timer) so a restart between midnight and 08:00 does not
# lose the pending message. Keys: "sleep", "systems".
PENDING_MESSAGE_PATH = "memory/pending_message.json"
DEFERRED_SEND_HOUR = 8
DEFERRED_SEND_MINUTE = 0

# Wake — entity discovery. Fixed time (the shell automation hardcoded 09:00).
WAKE_TIME = "09:00"
SENSITIVE_DEVICE_CLASSES = frozenset({
    "water", "moisture", "smoke", "gas", "carbon_monoxide", "safety", "tamper",
})
SENSITIVE_DOMAINS = frozenset({"alarm_control_panel"})

# Sleep — pause between the briefing call and the memory-extraction call.
SLEEP_EXTRACTION_DELAY_SECONDS = 5
# Cap on events serialized into the extraction prompt (busy days must not
# blow the provider context window).
SLEEP_EXTRACTION_MAX_EVENTS = 100
EVENT_SLEEP_COMPLETE = "permear_sleep_consolidation_complete"

# =============================================================================
# v9.0-final — error monitor, Telegram handler, HA updates
# =============================================================================

# Error monitor (ports lib/logs.py + permear_config.py lists). Errors NEVER
# enter the event buffer or ARAS — they go straight to a Telegram card.
NOISY_COMPONENTS = (
    "recorder", "statistics", "logbook", "history",
    "speedtestdotnet", "msmart",
    "frontend.js",
    "webostv", "aiowebostv",  # LG TV emits a cosmetic error when it sleeps
)
SELF_COMPONENTS = (
    "telegram_bot", "telegram", "conversation",
    "google_generative_ai", "google_ai",
    "shell_command", "automation",
)
TRANSIENT_MSG_KEYWORDS = (
    "clientconnectionreseterror",
    "cannot write to closing transport",
    "connectionreseterror",
)
# Gemini content-policy blocks (the integration logs e.g. "Error in Google
# Generative AI response: FinishReason.SAFETY, see: ..."). These are EXTERNAL
# provider decisions resolved by the fallback choreography — never a PERMEAR
# bug. Matched ONLY inside the google_generative_ai branch of
# is_provider_transient (never globally — the bare word "safety" in another
# component's error must not be swallowed). MAX_TOKENS / OTHER /
# MALFORMED_FUNCTION_CALL are deliberately excluded: those can signal a real
# config or code problem, not an external content block.
GOOGLE_BLOCK_FINISH_REASONS = (
    "finishreason.safety",
    "finishreason.recitation",
    "finishreason.blocklist",
    "finishreason.prohibited_content",
    "finishreason.spii",
)
ERROR_ARCHIVE_EXPIRATION_HOURS = 24
# Flood guard — ports the shell's queued(max 5) + 10-min tail delay.
ERROR_CARD_WINDOW_SECONDS = 600
ERROR_CARD_MAX_PER_WINDOW = 5

# Telegram handler.
TELEGRAM_DEDUP_TTL_SECONDS = 24 * 3600  # in-memory (replaces daily_ DB flags)
TELEGRAM_CONFIRM_WORDS = frozenset({"sim", "yes", "ok", "confirmo", "approve"})
TELEGRAM_REJECT_WORDS = frozenset(
    {"não", "nao", "cancel", "cancelar", "no", "reject"}
)
CONVERSATION_RETRY_DELAYS = (0, 15, 45)  # 3 attempts per provider
REACTION_WINDOW_MINUTES = 15  # user reply marks recent emits as reacted

# Agent automations (CRUD over automations/permear_agent.yaml).
MAX_AGENT_AUTOMATIONS = 20
# Action domains an agent-created automation may call. Closed allowlist —
# the action_service comes from the LLM; anything outside (homeassistant.*,
# shell_command.*, python_script.*, …) is rejected before the spec is built.
AGENT_ACTION_DOMAINS = frozenset({
    "light", "switch", "climate", "cover", "media_player", "fan", "lock",
})
SPEC_ENTITY_DOMAINS = (  # entity list injected into the spec-creation prompt
    "light", "switch", "climate", "media_player",
    "cover", "sensor", "binary_sensor",
)

# HA update cards — daily check (was attached to the shell Sleep block; now
# scheduled right after Wake, morning slot).
UPDATES_TIME = "09:05"
