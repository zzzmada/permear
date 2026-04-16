#!/bin/bash
# PERMEAR Installation Script
# Original by clyra (https://github.com/clyra), improved in v5.5
set -e

DEFAULT_BASE_DIR="/config"
DEFAULT_AUTOMATION_DIR="automations"
DEFAULT_MEMORY_DIR="memory"
DEFAULT_DAILY_DIR="daily"
DEFAULT_LOGS_DIR="logs"
DEFAULT_SCRIPT_DIR="scripts"
DEFAULT_AUTOMATION_FILE="agent_automations.yaml"

INSTALL_DIR="${1:-${DEFAULT_BASE_DIR}}"
AUTOMATION_DIR="${INSTALL_DIR}/${2:-${DEFAULT_AUTOMATION_DIR}}"
SCRIPT_DIR="${INSTALL_DIR}/${3:-${DEFAULT_SCRIPT_DIR}}"
PACKAGE_DIR="$4"

MEMORY_DIR="${INSTALL_DIR}/${DEFAULT_MEMORY_DIR}"
DAILY_DIR="${MEMORY_DIR}/${DEFAULT_DAILY_DIR}"
LOGS_DIR="${INSTALL_DIR}/${DEFAULT_LOGS_DIR}"
TOKEN_FILE="${INSTALL_DIR}/.permear_token"
SECRETS_FILE="${INSTALL_DIR}/secrets.yaml"

if [ "$1" == "--help" ] || [ "$1" == "-h" ]; then
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
    exit 0
fi

echo "=========================================="
echo "  PERMEAR v5.5 — Installation Script"
echo "=========================================="
echo ""
echo "Target directories:"
echo "  BASE_DIR:       $INSTALL_DIR"
echo "  AUTOMATION_DIR: $AUTOMATION_DIR"
echo "  SCRIPT_DIR:     $SCRIPT_DIR"
echo "  MEMORY_DIR:     $MEMORY_DIR"
echo "  DAILY_DIR:      $DAILY_DIR"
echo "  LOGS_DIR:       $LOGS_DIR"
if [ -n "$PACKAGE_DIR" ]; then
    echo "  PACKAGE_DIR:    $INSTALL_DIR/$PACKAGE_DIR"
fi
echo ""
read -p "Proceed? [y/N]: " ans && [[ "$ans" =~ ^[Yy]$ ]] || exit 1

# Step 1: Directories
echo ""
echo ">>> Step 1: Creating directories..."
mkdir -p "$DAILY_DIR"
mkdir -p "$SCRIPT_DIR"
mkdir -p "$LOGS_DIR"
touch "$AUTOMATION_DIR/$DEFAULT_AUTOMATION_FILE"
echo "  OK: directories created."

# Step 2: Access token
echo ""
echo ">>> Step 2: Access token..."
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
    echo -e "\n  Token saved to $TOKEN_FILE"
fi

# Step 3: Secrets
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

# Step 4: Copy files
echo ""
echo ">>> Step 4: Copying files..."

SCRIPTS_SRC="./scripts"
MEMORY_SRC="./memory"
AUTOMATIONS_SRC="./automations"

if [ -d "$SCRIPTS_SRC" ]; then
    # Protect user's permear_config.py from overwrite
    if [ -f "$SCRIPT_DIR/permear_config.py" ]; then
        chattr +i "$SCRIPT_DIR/permear_config.py" 2>/dev/null || true
    fi
    cp "$SCRIPTS_SRC"/*.py "$SCRIPT_DIR/" 2>/dev/null || true
    if [ -f "$SCRIPT_DIR/permear_config.py" ]; then
        chattr -i "$SCRIPT_DIR/permear_config.py" 2>/dev/null || true
    fi
    echo "  Copied scripts to $SCRIPT_DIR/"
else
    echo "  [WARNING] Scripts directory not found: $SCRIPTS_SRC"
fi

if [ -d "$MEMORY_SRC" ]; then
    if [ -f "$MEMORY_DIR/soul.json" ]; then
        echo "  Memory files exist — not overwriting (your agent has a soul)."
    else
        cp "$MEMORY_SRC"/*.json "$MEMORY_DIR/" 2>/dev/null || true
        echo "  Copied memory templates to $MEMORY_DIR/"
    fi
else
    echo "  [WARNING] Memory directory not found: $MEMORY_SRC"
fi

if [ -d "$AUTOMATIONS_SRC" ]; then
    cp "$AUTOMATIONS_SRC"/*.yaml "$AUTOMATION_DIR/" 2>/dev/null || true
    echo "  Copied automations to $AUTOMATION_DIR/"
else
    echo "  [WARNING] Automations directory not found: $AUTOMATIONS_SRC"
fi

# Step 5: Lock guidelines
GUIDELINES_FILE="$MEMORY_DIR/guidelines.json"
if [ -f "$GUIDELINES_FILE" ]; then
    echo ""
    echo ">>> Step 5: Locking guidelines..."
    chmod 444 "$GUIDELINES_FILE"
    echo "  Locked $GUIDELINES_FILE (read-only)"
fi

# Step 6: Package configuration
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

echo ""
echo "=========================================="
echo "  Installation Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Set max_tokens to 8192+ in your LLM integration"
echo "  2. Customize permear_config.py (paths, day names, limits)"
echo "  3. Customize soul.json, users.json (edit before locking guidelines)"
echo "  4. Configure Telegram bot in HA (polling mode)"
echo "  5. Update your LLM system prompt (see README)"
echo "  6. Restart Home Assistant"
echo "  7. Run initial discovery: Developer Tools → Services → shell_command.discover_entities"
echo ""
