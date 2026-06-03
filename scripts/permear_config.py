"""
PERMEAR — Centralized configuration.
All scripts import paths and constants from here.
"""
import yaml
from pathlib import Path

_PERMEAR_YAML_PATH = Path("/config/permear.yaml")


def _load_permear_config() -> dict:
    """Load /config/permear.yaml. Fatal error if it does not exist."""
    if not _PERMEAR_YAML_PATH.exists():
        raise RuntimeError(
            f"Missing configuration file: {_PERMEAR_YAML_PATH}. "
            "Create it from the template in docs/configuration.md."
        )
    with open(_PERMEAR_YAML_PATH) as f:
        return yaml.safe_load(f)


_permear_cfg = _load_permear_config()
_providers = _permear_cfg.get("providers", {})
_cycles    = _permear_cfg.get("cycles", {})

# Provider slots exposed to Python scripts
CONVERSATION_PROVIDER = _providers["conversation"]
DATA_PROVIDER = _providers["data"]
CONVERSATION_FALLBACK = _providers["conversation_fallback"]
DATA_FALLBACK = _providers["data_fallback"]

# Cycle schedules — read from permear.yaml, synced to input_datetime entities at startup
CYCLES_HEARTBEAT_START = _cycles.get("heartbeat_start", "08:30")
CYCLES_HEARTBEAT_END   = _cycles.get("heartbeat_end",   "20:00")
CYCLES_SLEEP_TIME      = _cycles.get("sleep_time",      "23:30")
CYCLES_SYSTEMS_TIME    = _cycles.get("systems_time",     "04:00")

# Paths
MEMORY_DIR = "/config/memory"
AGENT_YAML = "/config/automations/permear_agent.yaml"  # agent-managed automations (CRUD via manage_agent_automations.py)
AUTOMATIONS_YAML = "/config/automations/events.yaml"
TOKEN_PATH = "/config/.permear_token"
HA_URL = "http://localhost:8123"
LOG_DIR = "/config/logs"
HA_LOG_PATH = "/config/home-assistant.log"
ENTITIES_PATH = "/config/memory/monitored_entities.json"
ENTITY_REGISTRY_PATH = "/config/.storage/core.entity_registry"
PENDING_SPEC_PATH = "/config/memory/pending_auto_spec.json"
AGENT_CIRCUIT_PATH = "/config/memory/agent_circuit.json"
ARCHIVED_ERRORS_PATH = "/config/memory/archived_errors.json"
INSIGHTS_ARCHIVED_PATH = "/config/memory/insights_archived.json"
GUIDELINES_PATH = "/config/memory/guidelines.json"

# Day names. Index matches datetime.weekday() (Monday=0).
# DAYS = internal label (English), used only in internal LLM context strings.
# DAYS_PT = user-facing display name (Portuguese, i18n) shown in briefings.
DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
DAYS_PT = [
    'Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira',
    'Sexta-feira', 'Sábado', 'Domingo'
]

# Primary resident — read from permear.yaml agent.primary_resident
PRIMARY_RESIDENT = _permear_cfg.get("agent", {}).get("primary_resident", "")

# Limits
MAX_ENTITIES = 80
MAX_AUTOMATIONS = 20
MAX_EVENTS_PER_DAY = 20
MAX_INTERACTIONS_PER_DAY = 10

# System components — errors from these are SELF_ERRORS (v5.4)
SELF_COMPONENTS = [
    "telegram_bot", "telegram", "conversation",
    "google_generative_ai", "google_ai",
    "shell_command", "automation"
]

# Noisy components — filtered out of the real-time error monitor
NOISY_COMPONENTS = [
    "recorder", "statistics", "logbook", "history",
    "speedtestdotnet", "msmart",
    "webostv", "aiowebostv",  # LG TV emits a cosmetic error when it sleeps
]


# ARAS Filter — salience thresholds
# The emit threshold is dynamic (computed per-Heartbeat by compute_dynamic_threshold).
# It starts at ARAS_THRESHOLD_MIN (newborn/curious) and grows toward ARAS_THRESHOLD_MAX
# (mature/selective) as the system consolidates memory of the household.
#
# MIN and MAX are derived from permear.yaml aras.sensitivity — the only parameter
# the user needs to touch. Everything else here is fixed calibration.
_SENSITIVITY_MAP = {
    "sensitive": (1, 3),   # more alerts, less filtering
    "balanced":  (2, 4),   # production-calibrated default (v7.9-C / SD4)
    "quiet":     (3, 5),   # fewer alerts, more selective
}
_sensitivity = _permear_cfg.get("aras", {}).get("sensitivity", "balanced")
_threshold_pair = _SENSITIVITY_MAP.get(_sensitivity, _SENSITIVITY_MAP["balanced"])
ARAS_THRESHOLD_MIN = _threshold_pair[0]
ARAS_THRESHOLD_MAX = _threshold_pair[1]

# Fixed calibration — not exposed to the user
ARAS_MATURITY_FULL_RATIO = 0.5    # ratio consolidated/exposed that counts as "mature"
ARAS_MATURITY_MIN_ENTITIES = 5    # minimum exposed entities before maturity scales up

# v7.6 — Interoception: thresholds for declining signals
BATTERY_THRESHOLD = 20          # % — below this becomes a candidate
BATTERY_ENTITY_PATTERNS = ["_battery", "_battery_level"]
BATTERY_DEVICE_CLASSES = ["battery"]

# v7.6-C — connectivity: silence detection
AVAILABILITY_PATH = "/config/memory/availability_snapshot.json"
SILENT_STATES = ("unavailable", "unknown")
# excluded domains: structural or presence state, not a hardware failure
SILENT_IGNORE_DOMAINS = [
    "device_tracker", "person",   # presence, flicker constantly
    "automation", "script",       # unknown/unavailable is structural, not a failure
    "button",                     # always unknown until pressed
    "stt", "tts", "notify",       # integration state, not hardware
    "update",                     # managed separately by ha_update_manager
]

# v7.7-B — Engagement-based priority learning (weekly adjustment)
ENGAGEMENT_MIN_ALERTS = 4       # minimum alerts to have confidence
ENGAGEMENT_UP_RATE = 0.66       # reaction rate >= raises priority
ENGAGEMENT_DOWN_RATE = 0.33     # reaction rate <= lowers priority

# === Organic Memory (v7.8+) — all parameters here, never hardcoded ===
# Future v9: migrate to an editable config.yaml. v10: GUI.
MEMORY_DB_PATH = "/config/memory/permear_memory.db"

MEMORY_EPHEMERAL_FADE_DAYS = 7        # ephemeral without mention -> fade
MEMORY_ACTIVE_PROMOTE_MENTIONS = 3    # mentions for ephemeral -> active
MEMORY_ACTIVE_PROMOTE_WINDOW = 30     # window (days)
MEMORY_STABLE_PROMOTE_MENTIONS = 10   # mentions for active -> stable
MEMORY_STABLE_PROMOTE_WINDOW = 90     # window (days)
MEMORY_ACTIVE_DEMOTE_DAYS = 30        # active without mention -> ephemeral
MEMORY_STABLE_DEMOTE_DAYS = 90        # stable without mention -> active
MEMORY_FTS_MIN_SCORE = -5.0           # FTS similarity threshold for "same memory"
                                       # (bm25: more negative = more similar)
                                       # v7.9-C: -1.5 caused false merges with a small corpus
                                       # (e.g. TV memory absorbed by curtains via the token "sala")
                                       # -5.0 requires strong semantic overlap before merging
