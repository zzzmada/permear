"""
PERMEAR — Centralized configuration.
All scripts import paths and constants from here.
Users with different directory structures only need to edit this file.
"""

# Paths
MEMORY_DIR = "/config/memory"
DAILY_DIR = "/config/memory/daily"
AGENT_YAML = "/config/automations/agent_automations.yaml"
AUTOMATIONS_YAML = "/config/automations/permear.yaml"
TOKEN_PATH = "/config/.permear_token"
HA_URL = "http://localhost:8123"
LOG_DIR = "/config/logs"
HA_LOG_PATH = "/config/home-assistant.log"
ENTITIES_PATH = "/config/memory/monitored_entities.json"
ENTITY_REGISTRY_PATH = "/config/.storage/core.entity_registry"

# v6.x — Pending automation spec (created via /new_automation flow)
PENDING_SPEC_PATH = "/config/memory/pending_auto_spec.json"

# v7.0 — Agent circuit breaker state
AGENT_CIRCUIT_PATH = "/config/memory/agent_circuit.json"
# v7.0 — Errors silenced for 24h via Telegram button
ARCHIVED_ERRORS_PATH = "/config/memory/archived_errors.json"
# v7.0 — Insights items archived after 30 days without mention
INSIGHTS_ARCHIVED_PATH = "/config/memory/insights_archived.json"

# Day names (must match daily filenames: monday.json, etc.)
# Change for your language. Example Portuguese:
# DAYS = ['segunda', 'terca', 'quarta', 'quinta', 'sexta', 'sabado', 'domingo']
DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
DAYS_DISPLAY = ['Monday', 'Tuesday', 'Wednesday', 'Thursday',
                'Friday', 'Saturday', 'Sunday']

# Limits
MAX_ENTITIES = 80
MAX_AUTOMATIONS = 20
MAX_EVENTS_PER_DAY = 20
MAX_INTERACTIONS_PER_DAY = 10

# v5.4 — Components used by PERMEAR — errors from these are SELF_ERRORS
SELF_COMPONENTS = [
    "telegram_bot", "telegram", "conversation",
    "google_generative_ai", "google_ai",
    "openrouter", "deepseek",
    "shell_command", "automation"
]

# v7.0 — Noisy components — filtered from real-time error monitor
# Add your own noisy integrations here.
NOISY_COMPONENTS = [
    "recorder", "statistics", "logbook", "history",
    "speedtestdotnet"
]


# ==============================================================================
# v7.1-H — AI Task entities (structured output via ai_task.generate_data)
# ==============================================================================
#
# Used in non-interactive cycles (briefing memory extraction, weekly compile,
# quick learning, automation creation). Interactive cycles (Telegram chat,
# voice) keep using conversation.process for native HA Tools support.
#
# Default (primary): OpenRouter DeepSeek (cheap, structured-output friendly).
# Default (secondary): Google AI Task (Gemini Flash, free tier).
#
# Customize entity IDs to match your HA setup. Both must be configured as
# AI Task entities via their respective integrations in HA Settings.
#
# See README.md "AI Provider Architecture" for setup details.
#
AI_TASK_PRIMARY = "ai_task.openrouter_deepseek_v3"
AI_TASK_SECONDARY = "ai_task.google_ai_task"
