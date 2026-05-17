# PERMEAR

**Persistent Memory Architecture for Home Assistant AI Agents**

PERMEAR transforms Home Assistant + LLMs into a persistent household assistant that remembers, learns, monitors, and improves over time.

Built and tested on Home Assistant OS running on a Raspberry Pi 4 (2 GB RAM).

---

## What This Is

Home Assistant conversation agents (Gemini, OpenAI, etc.) are normally stateless. Every interaction starts from zero.

PERMEAR adds long-term memory, reflection cycles, health monitoring, automation management, and proactive behavior using a lightweight file-based architecture fully integrated with Home Assistant.

The assistant evolves from a simple chatbot into a system caretaker capable of:

- Remembering users, preferences, and patterns
- Monitoring Home Assistant health and errors
- Generating proactive Telegram briefings
- Creating native HA automations with confirmation
- Detecting updates and new devices
- Learning restrictions from user feedback
- Maintaining long-term contextual memory

No external database. No vector store. No cloud memory backend.

Everything is local, file-based, and HA-native.

---

# Architecture

## Persistent memory

```text
memory/
├── guidelines.json
│   Immutable constitution and behavioral rules
│
├── soul.json
│   Agent personality and long-term traits
│
├── users.json
│   Household profiles and learned preferences
│
├── insights.json
│   Patterns, pending tasks, recurring observations
│
├── monitored_entities.json
│   Single source of truth for monitored entities
│
└── daily/
    └── monday..sunday.json
        Rotating 7-day memory logs
````

---

## Core scripts

```text
scripts/
├── permear_config.py
│   Centralized constants and paths
│
├── append_daily.py
│   Save events, memories, interactions
│
├── build_prebriefing.py
│   Proactive house evaluation cycle
│
├── build_briefing.py
│   Daily briefing generation
│
├── weekly_compile.py
│   Long-term memory consolidation
│
├── apply_quick_learning.py
│   Learns restrictions from feedback
│
├── discover_entities.py
│   Auto-discovers exposed entities
│
├── ha_log_monitor.py
│   HA log parsing and filtering
│
├── manage_agent_automations.py
│   Create/remove/list automations
│
├── circuit_breaker.py
│   LLM reliability and fallback handling
│
└── lib/
    ├── memory.py
    ├── logs.py
    └── agent.py
```

---

## Runtime cycles

```text
Every 30 min (08:00–20:00)
└── Pre-briefing
    Evaluate house state and decide whether to notify

Daily 21:00
└── Daily briefing
    Summary, pending items, updates, memories

Daily 06:00
└── Entity discovery
    Sync exposed HA entities automatically

Sunday 00:05
└── Weekly compilation
    Long-term reflection and memory updates

Real-time
└── Error monitor
    Detect and filter HA / agent issues
```

---

# LLM Architecture

PERMEAR intentionally separates interactive and non-interactive AI tasks.

| Path                    | Purpose                                             |
| ----------------------- | --------------------------------------------------- |
| `conversation.process`  | Telegram chat and voice control                     |
| `ai_task.generate_data` | Briefings, memory extraction, automation generation |

This architecture allows:

* Fast interactive responses
* Cheap background processing
* Structured outputs without parsing hacks
* Automatic fallback between providers
* Better long-term reliability

Typical setup:

| Provider                | Usage                 |
| ----------------------- | --------------------- |
| Gemini Flash            | Interactive assistant |
| DeepSeek via OpenRouter | Background cycles     |

---

# Features

## Persistent memory

The assistant maintains long-term memory across days and weeks using JSON-based files.

---

## Proactive briefings

PERMEAR generates:

* House summaries
* Device alerts
* Update notifications
* Pending reminders
* Important contextual observations

Only when relevant.

Silence is considered valid behavior.

---

## Automation creation

Users can request automations naturally through Telegram.

Example:

```text
Turn off all lights at 1 AM if nobody is home
```

The assistant generates a native Home Assistant automation proposal and asks for confirmation before creation.

---

## Health monitoring

PERMEAR monitors:

* Home Assistant errors
* Integration failures
* LLM failures
* Rate limits
* Internal agent errors

Critical issues are reported automatically.

---

## Active forgetting

Old patterns and stale pending items are archived automatically after extended inactivity.

This prevents memory pollution over time.

---

# Requirements

* Home Assistant OS or Supervised
* Telegram Bot integration
* Gemini or compatible conversation agent
* AI Task integration
* Python 3.11+
* Long-lived HA token

Recommended:

* Gemini Flash for interaction
* DeepSeek V4 Flash for background tasks

---

# Quick Install

```bash id="zk3b2p"
cd /config
wget https://raw.githubusercontent.com/zzzmada/permear/main/install.sh
bash install.sh
```

---

# Repository Structure

```text
permear/
├── automations/
├── docs/
├── memory/
├── scripts/
├── CHANGELOG.md
├── MIGRATION.md
├── README.md
├── install.sh
└── configuration_additions.yaml
```

---

# Philosophy

PERMEAR prioritizes simplicity and Home Assistant native architecture.

Core principles:

* No overengineering
* No unnecessary abstractions
* No external infrastructure
* Single source of truth
* File-based persistence
* Human-readable state
* HA-native workflows first

---

# Status

Current public release: `v7.2.0`

See:

* `CHANGELOG.md`
* `MIGRATION.md`
* `docs/customization.md`

---

# License

MIT License

---

# Credits

* Author: @zzzmada
* Installer improvements: @clyra
* Built around Home Assistant ecosystem

```
```
