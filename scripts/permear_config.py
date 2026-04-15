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

# Day names (must match daily filenames: monday.json, etc.)
# For non-English setups, change to match your file names.
DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
DAYS_DISPLAY = ['Monday', 'Tuesday', 'Wednesday', 'Thursday',
                'Friday', 'Saturday', 'Sunday']

# Limits
MAX_ENTITIES = 80
MAX_AUTOMATIONS = 20
MAX_EVENTS_PER_DAY = 20
MAX_INTERACTIONS_PER_DAY = 10

# Components used by PERMEAR — errors from these are SELF_ERRORS
# (the agent caused them, not external factors)
SELF_COMPONENTS = [
    "telegram_bot", "telegram", "conversation",
    "google_generative_ai", "google_ai",
    "shell_command", "automation"
]
