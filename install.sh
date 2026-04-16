#!/bin/bash

set -e

DEFAULT_BASE_DIR="/config"
DEFAULT_AUTOMATION_DIR="automation"
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
LOGS_DIR="${INSTALL_DIR}/$DEFAULT_LOGS_DIR"
TOKEN_FILE="${INSTALL_DIR}/.permear_token"

if [ "$1" == "--help" ] || [ "$1" == "-h" ]; then
    echo "Usage: $0 [BASE_DIR] [AUTOMATION_DIR] [SCRIPT_DIR] [PACKAGE_DIR]"
    echo ""
    echo "For automation, script and package use relative dir_name only"
    echo "myautomations, not /config/myautomations"
    echo ""
    echo "Defaults:"
    echo "  BASE_DIR=$DEFAULT_BASE_DIR"
    echo "  AUTOMATION_DIR=$BASE_DIR/$DEFAULT_AUTOMATION_DIR"
    echo "  SCRIPT_DIR=$BASE_DIR/$DEFAULT_SCRIPT_DIR"
    echo "  PACKAGE_DIR (no default)"
    exit 0
fi

if [ -z "$1" ] && [ -z "$BASE_DIR" ]; then
    BASE_DIR="$DEFAULT_BASE_DIR"
fi

echo "=========================================="
echo "  PERMEAR Installation Script"
echo "=========================================="
echo ""
echo "Target directories:"
echo "  BASE_DIR:       $INSTALL_DIR"
echo "  AUTOMATION_DIR: $AUTOMATION_DIR"
echo "  SCRIPT_DIR:     $SCRIPT_DIR"
echo "  MEMORY_DIR:     $MEMORY_DIR"
echo "  DAILY_DIR:      $DAILY_DIR"
echo "  LOGS_DIR:       $LOGS_DIR"
echo "  PACKAGE_DIR:    $INSTALL_DIR/$PACKAGE_DIR"
echo ""

read -p "Proceed? [y/N]: " ans && [[ "$ans" =~ ^[Yy]$ ]] || exit 1

echo ""
echo ">>> Step 1: Creating directories..."
mkdir -p "$DAILY_DIR" 
mkdir -p "$SCRIPT_DIR" 
mkdir -p "$LOGS_DIR" 
touch "$AUTOMATION_DIR/$DEFAULT_AUTOMATION_FILE"
echo "Directories created:"
echo "  - $DAILY_DIR"
echo "  - $SCRIPT_DIR"
echo "  - $LOGS_DIR"
echo "  - $AUTOMATION_DIR/$DEFAULT_AUTOMATION_FILE"

echo ""
echo ">>> Step 2: Creating access token file..."
echo ""
echo "  To create a token:"
echo "  1. Go to HA sidebar → your profile"
echo "  2. Long-Lived Access Tokens → Create"
echo "  3. Name it 'PERMEAR'"
echo ""

if [ -f "$TOKEN_FILE" ]; then
    echo "  Token file already exists at $TOKEN_FILE"
    echo -n "  Replace it? [y/N]: "
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        echo "  Enter your HA Long-Lived Access Token:"
        read -r -s TOKEN
        echo "$TOKEN" > "$TOKEN_FILE"
        chmod 600 "$TOKEN_FILE"
        echo "  Token updated."
    else
        echo "  Keeping existing token."
    fi
else
    echo -n "  Enter your HA Long-Lived Access Token: "
    read -r -s TOKEN
    echo "$TOKEN" > "$TOKEN_FILE"
    chmod 600 "$TOKEN_FILE"
    echo ""
    echo "  Token saved to $TOKEN_FILE"
fi

echo ""
echo ">>> Step 3: Copying files..."
echo ""

SCRIPTS_SRC="./scripts"
MEMORY_SRC="./memory"
AUTOMATIONS_SRC="./automations"

if [ -d "$SCRIPTS_SRC" ]; then
echo 
    chattr +i  "$SCRIPT_DIR/permear_config.py"
    cp "$SCRIPTS_SRC"/*.py "$SCRIPT_DIR/" 2>/dev/null || true
    chattr -i  "$SCRIPT_DIR/permear_config.py" 
    echo "  Copied scripts to $SCRIPT_DIR/"
else
    echo "  [WARNING] Scripts directory not found: $SCRIPTS_SRC"
fi

if [ -d "$MEMORY_SRC" ]; then
    if [ -f "$MEMORY_DIR/soul.json" ]; then
        echo "  You already have a soul. I will not touch memory dir"
    else
       cp "$MEMORY_SRC"/*.json "$MEMORY_DIR/" 2>/dev/null || true
       echo "  Copied memory files to $MEMORY_DIR/"
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

GUIDELINES_FILE="$MEMORY_DIR/guidelines.json"
if [ -f "$GUIDELINES_FILE" ]; then
    echo ""
    echo ">>> Step 4: Locking guidelines..."
    chmod 444 "$GUIDELINES_FILE"
    echo "  Locked $GUIDELINES_FILE (read-only)"
else
    echo ""
    echo "  [WARNING] guidelines.json not found at $GUIDELINES_FILE"
fi

echo ""
echo ">>> Step 5: extra configuration"
echo ""

if [ -z "$PACKAGE_DIR" ]; then
    echo "  There's no package_dir and we will not change your configuration.yaml."
    echo "  Make sure you added the contents of configuration_additions.yaml"
    echo "  to your configuration."

else
    cp configuration_additions.yaml $INSTALL_DIR/$PACKAGE_DIR
    echo "  Additional configuration copied to $PACKAGE_DIR"
fi


echo ""
echo "=========================================="
echo "  Installation Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  4. Set max_tokens to 8192+ in your LLM integration"
echo "  7. Customize permear_config.py, soul.json, users.json, guidelines.json"
echo "  9. Configure Telegram bot (polling mode)"
echo "  10. Add automations and replace placeholders (YOUR_CHAT_ID, YOUR_AGENT_ID)"
echo "  11. Update LLM system prompt"
echo "  12. Run initial discovery and restart Home Assistant"
echo ""
