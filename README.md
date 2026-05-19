# PERMEAR

**Persistent Memory and Salience Filter for Home Assistant.**

An AI memory layer that learns what matters in your home — and stays silent about what doesn't.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-7.3.0-blue.svg)](CHANGELOG.md)
[![HAOS](https://img.shields.io/badge/Home%20Assistant-2025.7+-blue.svg)](https://www.home-assistant.io/)
[![RPi4 2GB](https://img.shields.io/badge/RPi4%202GB-supported-green.svg)](https://www.raspberrypi.com/)

---

## What you get

📔 **Persistent memory** — daily, weekly, indefinite (JSON files, no database)
🔔 **Proactive Telegram contact** — alerts when something matters, silence when it doesn't
🧠 **Daily and weekly self-reflection** — distills events into reusable patterns
✨ **Automation by chat** — describe what you want, agent proposes, you confirm
🗑 **Active forgetting** — items not seen in 30 days move to archive
❤️ **Health monitoring** — circuit breaker, retry, automatic provider fallback
🔇 **Smart error filtering** — real HA errors come to Telegram, noise stays out

Runs on **Home Assistant OS** including **Raspberry Pi 4 with 2 GB RAM**. Estimated cost: **~$0.10/month** in LLM tokens.

---

## How it works

Two LLM paths kept intentionally separate:

| Path | Used for | Provider |
|---|---|---|
| `conversation.process` | Telegram chat, voice — needs HA Tools | Gemini Flash (free tier) |
| `ai_task.generate_data` | Briefings, weekly compile, automation creation | DeepSeek V4-Flash via OpenRouter |

Every non-interactive call has automatic fallback: **DeepSeek → Gemini** if primary fails. The `sensor.permear_health` reflects state in real time.

---

## Cycles

| Cycle | When | What |
|---|---|---|
| Pre-briefing | Hourly, 08:30–20:00 | Decides if you need to know (mostly silent) |
| Daily briefing | 23:30 | 120-word day summary + memory extraction |
| Entity discovery | 06:00 | Syncs with HA entity registry |
| Weekly compilation | Sunday 04:00 | 3 focused LLM calls update perennial memory |
| Real-time error monitor | Continuous | Filters noise, alerts on genuine errors |

---

## Looking ahead — the v10 vision

PERMEAR is evolving toward something more ambitious than "another HA automation pack":

> *A memory and salience layer for the household, inspired by neurological filtering. Only events that pass the **ARAS Filter** (Ascending Reticular Activating System analog) reach the user. Memory decays through three biological tiers — ephemeral, active, stable — reinforced by repeated mentions.*
>
> *Built by a pathologist applying neurological principles to home automation.*

The full plan is in [ROADMAP.md](ROADMAP.md). v7.3 is the stable foundation; v7.5+ introduces ARAS Filter and memory tiers; v10.0 will be the first HACS release.

---

## Quick install

```bash
# SSH or Terminal addon on your HA instance
cd /tmp
git clone https://github.com/zzzmada/permear
cd permear
bash install.sh
```

Follow the prompts. **Full guide:** [docs/install.md](docs/install.md).

**Upgrading?** See [MIGRATION.md](MIGRATION.md).

---

## Requirements

- Home Assistant OS or Supervised, **2025.7+** (native `ai_task.generate_data`)
- **Telegram bot** integration (polling mode)
- **Two LLM integrations:**
  - Google Generative AI (free tier OK) — for interactive paths
  - OpenRouter or DeepSeek — for `ai_task` cycles (~$0.10/month)
- ~50 MB disk, **RPi4 2 GB RAM** is enough

See [docs/byok.md](docs/byok.md) for the recommended **DeepSeek via OpenRouter BYOK setup** ($5 lasts ~4 years).

---

## Telegram commands

| Command | Effect |
|---|---|
| Type anything | Talks to the agent, can control devices |
| `/new_automation` | Starts automation creation flow with [Create] [Adjust] [Discard] |
| `/list_automations` | Shows agent-created automations with [Remove N] per row |
| Reply "I know" / "irrelevant" / "don't alert" | Agent learns a restriction |

---

## Customize

After installation, edit `/config/memory/`:

- `soul.json` — agent personality
- `users.json` — resident profiles
- `monitored_entities.json` — set `events:` per entity to log to daily

See [docs/customization.md](docs/customization.md) for the full guide.

---

## Lovelace card

Show PERMEAR health on your dashboard. Paste [memory/lovelace_card.yaml](memory/lovelace_card.yaml) into your dashboard's **Raw configuration editor**.

Displays 🟢 / 🟡 / 🟠 / 🔴 state + fallback usage + circuit breaker status.

---

## Contributing

PRs welcome. Principles:

1. **Simple, HA-native, no overengineering.**
2. **Single source of truth** — don't duplicate state across files.
3. **English everywhere** in this public repo.
4. **Backward compatibility** where reasonable.

Open issues at https://github.com/zzzmada/permear/issues.

---

## License & Credits

MIT — see [LICENSE](LICENSE).

Author: [@zzzmada](https://github.com/zzzmada) · Installer: [@clyra](https://github.com/clyra)
