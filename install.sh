#!/bin/bash
<<<<<<< HEAD
# PERMEAR Installation Script
# Original by clyra (https://github.com/clyra), improved in v5.5
=======
# PERMEAR v7.2 Installation Script
# Original by clyra (https://github.com/clyra), updated for v7.2.0
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
set -e

DEFAULT_BASE_DIR="/config"
DEFAULT_AUTOMATION_DIR="automations"
DEFAULT_MEMORY_DIR="memory"
DEFAULT_DAILY_DIR="daily"
<<<<<<< HEAD
DEFAULT_LOGS_DIR="logs"
DEFAULT_SCRIPT_DIR="scripts"
DEFAULT_AUTOMATION_FILE="agent_automations.yaml"
=======
DEFAULT_SCRIPT_DIR="scripts"
DEFAULT_LIB_DIR="lib"
DEFAULT_AGENT_FILE="agent_automations.yaml"
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)

INSTALL_DIR="${1:-${DEFAULT_BASE_DIR}}"
AUTOMATION_DIR="${INSTALL_DIR}/${2:-${DEFAULT_AUTOMATION_DIR}}"
SCRIPT_DIR="${INSTALL_DIR}/${3:-${DEFAULT_SCRIPT_DIR}}"
<<<<<<< HEAD
=======
LIB_DIR="${SCRIPT_DIR}/${DEFAULT_LIB_DIR}"
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
PACKAGE_DIR="$4"

MEMORY_DIR="${INSTALL_DIR}/${DEFAULT_MEMORY_DIR}"
DAILY_DIR="${MEMORY_DIR}/${DEFAULT_DAILY_DIR}"
<<<<<<< HEAD
LOGS_DIR="${INSTALL_DIR}/${DEFAULT_LOGS_DIR}"
=======
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
TOKEN_FILE="${INSTALL_DIR}/.permear_token"
SECRETS_FILE="${INSTALL_DIR}/secrets.yaml"

if [ "$1" == "--help" ] || [ "$1" == "-h" ]; then
<<<<<<< HEAD
    echo "Usage: $0 [BASE_DIR] [AUTOMATION_DIR] [SCRIPT_DIR] [PACKAGE_DIR]"
    echo ""
    echo "For automation, script and package use relative dir_name only:"
    echo "  myautomations, not /config/myautomations"
    echo ""
    echo "Defaults:"
    echo "  BASE_DIR=$DEFAULT_BASE_DIR"
    echo "  AUTOMATION_DIR=\$BASE_DIR/$DEFAULT_AUTOMATION_DIR"
    echo "  SCRIPT_DIR=\$BASE_DIR/$DEFAULT_SCRIPT_DIR"
    echo "  PACKAGE_DIR (optional, for HA packages)"
    echo ""
    echo "Examples:"
    echo "  $0                                    # All defaults"
    echo "  $0 /config automations scripts packages   # With HA packages"
    echo "  $0 /config automation.d script.d      # Custom dirs"
=======
    cat <<EOF
Usage: $0 [BASE_DIR] [AUTOMATION_DIR] [SCRIPT_DIR] [PACKAGE_DIR]

For automation, script and package, pass relative dir_name only:
  myautomations, not /config/myautomations

Defaults:
  BASE_DIR=$DEFAULT_BASE_DIR
  AUTOMATION_DIR=\$BASE_DIR/$DEFAULT_AUTOMATION_DIR
  SCRIPT_DIR=\$BASE_DIR/$DEFAULT_SCRIPT_DIR
  PACKAGE_DIR (optional, for HA packages)

Examples:
  $0                                    # All defaults
  $0 /config automations scripts packages
EOF
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
    exit 0
fi

echo "=========================================="
<<<<<<< HEAD
echo "  PERMEAR v5.5 — Installation Script"
=======
echo "  PERMEAR v7.2.0 — Installation Script"
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
echo "=========================================="
echo ""
echo "Target directories:"
echo "  BASE_DIR:       $INSTALL_DIR"
echo "  AUTOMATION_DIR: $AUTOMATION_DIR"
echo "  SCRIPT_DIR:     $SCRIPT_DIR"
<<<<<<< HEAD
echo "  MEMORY_DIR:     $MEMORY_DIR"
echo "  DAILY_DIR:      $DAILY_DIR"
echo "  LOGS_DIR:       $LOGS_DIR"
if [ -n "$PACKAGE_DIR" ]; then
    echo "  PACKAGE_DIR:    $INSTALL_DIR/$PACKAGE_DIR"
fi
echo ""
read -p "Proceed? [y/N]: " ans && [[ "$ans" =~ ^[Yy]$ ]] || exit 1

echo ""
echo ">>> Step 1: Creating directories..."
mkdir -p "$DAILY_DIR"
mkdir -p "$SCRIPT_DIR"
mkdir -p "$LOGS_DIR"
touch "$AUTOMATION_DIR/$DEFAULT_AUTOMATION_FILE"
echo "  OK: directories created."

echo ""
echo ">>> Step 2: Access token..."
=======
echo "  LIB_DIR:        $LIB_DIR"
echo "  MEMORY_DIR:     $MEMORY_DIR"
echo "  DAILY_DIR:      $DAILY_DIR"
[ -n "$PACKAGE_DIR" ] && echo "  PACKAGE_DIR:    $INSTALL_DIR/$PACKAGE_DIR"
echo ""
read -p "Proceed? [y/N]: " ans && [[ "$ans" =~ ^[Yy]$ ]] || exit 1

# -----------------------------------------------------------------------------
# Step 1: Create directories
# -----------------------------------------------------------------------------
echo ""
echo ">>> Step 1: Creating directories..."
mkdir -p "$DAILY_DIR" "$SCRIPT_DIR" "$LIB_DIR" "$AUTOMATION_DIR"

# Ensure agent_automations.yaml exists with valid empty content
if [ ! -f "$AUTOMATION_DIR/$DEFAULT_AGENT_FILE" ]; then
    echo "[]" > "$AUTOMATION_DIR/$DEFAULT_AGENT_FILE"
fi
echo "  OK: directories created."

# -----------------------------------------------------------------------------
# Step 2: HA access token
# -----------------------------------------------------------------------------
echo ""
echo ">>> Step 2: Home Assistant access token..."
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
echo "  To create: HA sidebar → profile → Long-Lived Access Tokens → Create"
echo ""
if [ -f "$TOKEN_FILE" ]; then
    echo "  Token already exists at $TOKEN_FILE"
    read -p "  Replace it? [y/N]: " response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        read -r -s -p "  Enter token: " TOKEN
        echo "$TOKEN" > "$TOKEN_FILE"
        chmod 600 "$TOKEN_FILE"
        echo -e "\n  Token updated."
    else
        echo "  Keeping existing token."
    fi
else
    read -r -s -p "  Enter your HA Long-Lived Access Token: " TOKEN
    echo "$TOKEN" > "$TOKEN_FILE"
    chmod 600 "$TOKEN_FILE"
<<<<<<< HEAD
    echo -e "\n  Token saved to $TOKEN_FILE"
fi

=======
    echo -e "\n  Token saved."
fi

# -----------------------------------------------------------------------------
# Step 3: secrets.yaml
# -----------------------------------------------------------------------------
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
echo ""
echo ">>> Step 3: secrets.yaml configuration..."
echo ""

NEEDS_SECRETS=false
if ! grep -q "permear_chat_id" "$SECRETS_FILE" 2>/dev/null; then
    NEEDS_SECRETS=true
fi

if [ "$NEEDS_SECRETS" = true ]; then
    echo "  PERMEAR needs 3 entries in your secrets.yaml."
    echo ""
    read -p "  Enter your Telegram chat_id (integer): " CHAT_ID
<<<<<<< HEAD
    read -p "  Enter your agent_id (e.g. conversation.google_ai_conversation): " AGENT_ID
    read -p "  Enter your person entity (e.g. person.john): " PERSON_ENTITY
    echo "" >> "$SECRETS_FILE"
    echo "# PERMEAR" >> "$SECRETS_FILE"
    echo "permear_chat_id: $CHAT_ID" >> "$SECRETS_FILE"
    echo "permear_agent_id: $AGENT_ID" >> "$SECRETS_FILE"
    echo "permear_person_entity: $PERSON_ENTITY" >> "$SECRETS_FILE"
    echo "  Secrets added to $SECRETS_FILE"
else
    echo "  PERMEAR secrets already exist in $SECRETS_FILE"
    echo "  Keeping existing values."
fi

=======
    read -p "  Enter your interactive agent_id (e.g. conversation.google_generative_ai_conversation): " AGENT_ID
    read -p "  Enter your person entity (e.g. person.alice): " PERSON_ENTITY
    {
        echo ""
        echo "# PERMEAR v7.2"
        echo "permear_chat_id: $CHAT_ID"
        echo "permear_agent_id: $AGENT_ID"
        echo "permear_person_entity: $PERSON_ENTITY"
    } >> "$SECRETS_FILE"
    echo "  Secrets added to $SECRETS_FILE"
else
    echo "  PERMEAR secrets already exist in $SECRETS_FILE — keeping existing values."
fi

# -----------------------------------------------------------------------------
# Step 4: Copy files
# -----------------------------------------------------------------------------
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
echo ""
echo ">>> Step 4: Copying files..."

SCRIPTS_SRC="./scripts"
<<<<<<< HEAD
MEMORY_SRC="./memory"
AUTOMATIONS_SRC="./automations"

if [ -d "$SCRIPTS_SRC" ]; then
    if [ -f "$SCRIPT_DIR/permear_config.py" ]; then
        chattr +i "$SCRIPT_DIR/permear_config.py" 2>/dev/null || true
    fi
    cp "$SCRIPTS_SRC"/*.py "$SCRIPT_DIR/" 2>/dev/null || true
    if [ -f "$SCRIPT_DIR/permear_config.py" ]; then
        chattr -i "$SCRIPT_DIR/permear_config.py" 2>/dev/null || true
    fi
    echo "  Copied scripts to $SCRIPT_DIR/"
=======
LIB_SRC="./scripts/lib"
MEMORY_SRC="./memory"
AUTOMATIONS_SRC="./automations"

# Scripts (including lib/)
if [ -d "$SCRIPTS_SRC" ]; then
    # Preserve user's permear_config.py customizations
    if [ -f "$SCRIPT_DIR/permear_config.py" ]; then
        cp "$SCRIPT_DIR/permear_config.py" "$SCRIPT_DIR/permear_config.py.bak"
        echo "  Backed up existing permear_config.py"
    fi

    cp "$SCRIPTS_SRC"/*.py "$SCRIPT_DIR/" 2>/dev/null || true
    chmod +x "$SCRIPT_DIR"/*.py 2>/dev/null || true

    if [ -d "$LIB_SRC" ]; then
        cp "$LIB_SRC"/*.py "$LIB_DIR/" 2>/dev/null || true
    fi

    echo "  Copied scripts to $SCRIPT_DIR/"
    echo "  Copied lib to $LIB_DIR/"
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
else
    echo "  [WARNING] Scripts directory not found: $SCRIPTS_SRC"
fi

<<<<<<< HEAD
if [ -d "$MEMORY_SRC" ]; then
    if [ -f "$MEMORY_DIR/soul.json" ]; then
        echo "  Memory files exist — not overwriting (your agent has a soul)."
    else
        cp "$MEMORY_SRC"/*.json "$MEMORY_DIR/" 2>/dev/null || true
=======
# Memory templates (only if no existing soul.json)
if [ -d "$MEMORY_SRC" ]; then
    if [ -f "$MEMORY_DIR/soul.json" ]; then
        echo "  Memory files exist — not overwriting (your agent has a soul)."
        echo "  If upgrading from v5.x, see MIGRATION.md for translating keys."
    else
        # Convert .example.json templates to live files
        for f in "$MEMORY_SRC"/*.example.json; do
            [ -f "$f" ] || continue
            base=$(basename "$f" .example.json)
            cp "$f" "$MEMORY_DIR/$base.json"
        done
        # Daily templates: one per weekday
        for day in monday tuesday wednesday thursday friday saturday sunday; do
            cp "$MEMORY_SRC/daily/monday.example.json" "$DAILY_DIR/$day.json" 2>/dev/null || true
        done
        # Copy non-example files (guidelines.json, lovelace_card.yaml)
        cp "$MEMORY_SRC/guidelines.json" "$MEMORY_DIR/" 2>/dev/null || true
        cp "$MEMORY_SRC/lovelace_card.yaml" "$MEMORY_DIR/" 2>/dev/null || true
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
        echo "  Copied memory templates to $MEMORY_DIR/"
    fi
else
    echo "  [WARNING] Memory directory not found: $MEMORY_SRC"
fi

<<<<<<< HEAD
if [ -d "$AUTOMATIONS_SRC" ]; then
    cp "$AUTOMATIONS_SRC"/*.yaml "$AUTOMATION_DIR/" 2>/dev/null || true
    echo "  Copied automations to $AUTOMATION_DIR/"
=======
# Automations
if [ -d "$AUTOMATIONS_SRC" ]; then
    cp "$AUTOMATIONS_SRC/permear.yaml" "$AUTOMATION_DIR/" 2>/dev/null || true
    echo "  Copied permear.yaml to $AUTOMATION_DIR/"
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
else
    echo "  [WARNING] Automations directory not found: $AUTOMATIONS_SRC"
fi

<<<<<<< HEAD
=======
# -----------------------------------------------------------------------------
# Step 5: Lock guidelines.json
# -----------------------------------------------------------------------------
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
GUIDELINES_FILE="$MEMORY_DIR/guidelines.json"
if [ -f "$GUIDELINES_FILE" ]; then
    echo ""
    echo ">>> Step 5: Locking guidelines..."
    chmod 444 "$GUIDELINES_FILE"
    echo "  Locked $GUIDELINES_FILE (read-only)"
fi

<<<<<<< HEAD
=======
# -----------------------------------------------------------------------------
# Step 6: configuration.yaml additions
# -----------------------------------------------------------------------------
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
echo ""
echo ">>> Step 6: Configuration..."
if [ -n "$PACKAGE_DIR" ]; then
    mkdir -p "$INSTALL_DIR/$PACKAGE_DIR"
    cp configuration_additions.yaml "$INSTALL_DIR/$PACKAGE_DIR/permear.yaml"
    echo "  Package copied to $INSTALL_DIR/$PACKAGE_DIR/permear.yaml"
    echo "  Make sure your configuration.yaml has:"
    echo "    homeassistant:"
    echo "      packages: !include_dir_named $PACKAGE_DIR"
else
    echo "  No PACKAGE_DIR specified."
    echo "  Add the contents of configuration_additions.yaml to your configuration.yaml manually."
fi

<<<<<<< HEAD
=======
# -----------------------------------------------------------------------------
# Done
# -----------------------------------------------------------------------------
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
echo ""
echo "=========================================="
echo "  Installation Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
<<<<<<< HEAD
echo "  1. Set max_tokens to 8192+ in your LLM integration"
echo "  2. Customize permear_config.py (paths, day names, limits)"
echo "  3. Customize soul.json, users.json (edit before locking guidelines)"
echo "  4. Configure Telegram bot in HA (polling mode)"
echo "  5. Update your LLM system prompt (see README)"
echo "  6. Restart Home Assistant"
echo "  7. Run initial discovery: Developer Tools → Services → shell_command.discover_entities"
echo ""
=======
echo ""
echo "  1. Configure your LLM integrations (see README.md → Configure LLMs):"
echo "     - Google Generative AI: for interactive Telegram/voice"
echo "     - OpenRouter: for ai_task non-interactive cycles (DeepSeek primary)"
echo "     - Google AI Task: secondary fallback"
echo ""
echo "  2. Verify AI_TASK_PRIMARY and AI_TASK_SECONDARY in permear_config.py"
echo "     match your actual entity IDs."
echo ""
echo "  3. Customize $MEMORY_DIR/soul.json and users.json for your household."
echo ""
echo "  4. Configure Telegram bot in HA (polling mode)."
echo ""
echo "  5. Restart Home Assistant."
echo ""
echo "  6. Run initial entity discovery:"
echo "     Developer Tools → Services → shell_command.discover_entities"
echo ""
echo "  7. (Optional) Paste lovelace_card.yaml into your Lovelace dashboard."
echo ""
echo "Full guide: README.md"
echo "Upgrading from v5.x? See MIGRATION.md"
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
