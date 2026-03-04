# Atlas — AI News Agent

A personal Telegram bot that delivers AI-curated news digests and answers questions in real time using web search. Tell it your interests, pick a delivery time, and get a concise briefing every day — by text or voice.

---

## Features

- **Personalized digests** — set topics like `AI, climate tech, NBA` and get 5–7 stories each day
- **Real-time web search** — every answer is sourced live, never from stale memory
- **Daily scheduling** — digest delivered at your chosen time (UTC), survives restarts
- **Follow-up Q&A** — ask anything; the bot searches and replies with cited sources
- **Voice messages** — send a voice note, get a voice reply (optional, requires OpenAI key)
- **Group chat support** — add to a group; bot responds only when @mentioned or replied-to
- **Privacy controls** — restrict access to specific Telegram user IDs
- **Agent-driven behaviour** — personality, rules, and skills defined in plain markdown files

---

## Tech Stack

| Layer | Technology |
|---|---|
| Bot framework | `python-telegram-bot` 20.7 (async) |
| AI + web search | Anthropic Claude Haiku + `web_search_20250305` |
| Voice transcription | OpenAI Whisper (`whisper-1`) |
| Voice synthesis | OpenAI TTS (`tts-1`, OGG/Opus) |
| Scheduler | APScheduler 3.10 (AsyncIOScheduler) |
| Database | SQLAlchemy 2.0 — SQLite (local) or PostgreSQL (production) |
| Deployment | Docker + Railway |

---

## Prerequisites

- Python 3.11+
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- An [Anthropic API key](https://console.anthropic.com) (required)
- An [OpenAI API key](https://platform.openai.com) (optional — enables voice features)

---

## Local Setup

**1. Clone and install dependencies**

```bash
git clone https://github.com/nayirong/news-agent.git
cd news-agent
pip install -r requirements.txt
```

**2. Configure environment**

```bash
cp .env.example .env
```

Open `.env` and fill in at minimum:

```env
TELEGRAM_BOT_TOKEN=your_token_here
ANTHROPIC_API_KEY=your_key_here
ALLOWED_USER_IDS=your_telegram_id   # find yours via @userinfobot
```

**3. Initialise the database**

```bash
python scripts/setup_db.py
```

**4. Start the bot**

```bash
python scripts/run_bot.py
```

---

## Configuration

All settings are read from environment variables. See `.env.example` for the full list.

### Required

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | From `@BotFather` |
| `ANTHROPIC_API_KEY` | From [console.anthropic.com](https://console.anthropic.com) |

### Privacy

| Variable | Default | Description |
|---|---|---|
| `ALLOWED_USER_IDS` | *(empty — open to all)* | Comma-separated Telegram user IDs allowed to use the bot |

### Voice *(optional)*

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | *(empty — voice disabled)* | From [platform.openai.com](https://platform.openai.com) |
| `WHISPER_LANGUAGE` | `en` | ISO 639-1 code for transcription. Empty = auto-detect |
| `VOICE_NAME` | `nova` | TTS voice: `alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer` |

### Database

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///news_agent.db` | SQLite for local dev; `postgresql://...` for production |

### Scheduler & Logging

| Variable | Default | Description |
|---|---|---|
| `DEFAULT_DELIVERY_TIME` | `08:00` | Default daily digest time (HH:MM UTC) |
| `DEFAULT_TIMEZONE` | `UTC` | IANA timezone for new users |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_FILE` | `logs/bot.log` | Log file path |

---

## Bot Commands

| Command | Description |
|---|---|
| `/start` | Onboard or greet returning users |
| `/help` | Show available commands and voice status |
| `/digest` | Generate an on-demand digest immediately |
| `/interests` | View your current interest list |
| `/settime HH:MM` | Change your daily digest time (UTC) |
| `/digesthere` | Send future digests to this chat (useful for groups) |
| `/reload` | Hot-reload agent markdown files without restarting |

**Setting interests:** Simply send a comma-separated message like `AI, Formula 1, geopolitics` — the bot detects it and sets your interests automatically.

---

## Agent Behaviour

The bot's personality and rules live in plain markdown — no code changes needed:

| File | Purpose |
|---|---|
| `0. Agents/News Agent/SOUL.md` | Personality, tone, communication style |
| `0. Agents/News Agent/RULES.md` | Hard constraints (always cite sources, never fabricate, etc.) |
| `0. Agents/News Agent/SKILLS.md` | Capabilities with triggers and output formats |

Edit any of these files and send `/reload` in Telegram to apply changes instantly.

---

## Railway Deployment

The repo ships with a `Dockerfile` and `railway.toml` ready for one-click deployment.

**1. Push to GitHub** (`.gitignore` already excludes `.env` and `*.db`)

**2. Create a new project at [railway.app](https://railway.app)** and connect your repo

**3. Add environment variables** in the Railway dashboard (use `.env.example` as reference)

**4. Add a PostgreSQL addon** for persistent storage — without it, SQLite data is lost on every redeploy. Set `DATABASE_URL` to the provided connection string.

Railway restarts the container automatically on failure (up to 10 retries, per `railway.toml`).

---

## Group Chat Setup

1. Add the bot to your Telegram group
2. In BotFather: `/mybots` → your bot → Bot Settings → Group Privacy → **Turn off**
3. Remove and re-add the bot to the group
4. The bot responds only when **@mentioned** or when someone **replies to a bot message**

---

## Project Structure

```
news-agent/
├── 0. Agents/
│   └── News Agent/
│       ├── SOUL.md           Agent personality & values
│       ├── RULES.md          Hard constraints
│       └── SKILLS.md         Capabilities with output formats
├── config/
│   └── settings.py           All configuration from environment variables
├── src/
│   ├── agent_loader.py       Reads markdown files → assembles system prompt
│   ├── ai/
│   │   ├── claude_client.py  Claude API wrapper with web search + agentic loop
│   │   └── agent_tools.py    Tools for interest/schedule management
│   ├── bot/
│   │   ├── telegram_bot.py   Command handlers, message routing
│   │   └── voice_handler.py  Whisper transcription + OpenAI TTS
│   ├── database/
│   │   ├── models.py         SQLAlchemy ORM (User, UserInterest, Conversation)
│   │   └── db_manager.py     DB operations singleton
│   ├── scheduler/
│   │   └── news_scheduler.py APScheduler — daily digest jobs
│   └── user/
│       └── profile_manager.py User profile facade (interests, delivery time)
├── scripts/
│   ├── run_bot.py            Main entry point
│   ├── setup_db.py           One-time DB initialisation
│   └── test_agent_loader.py  Smoke test for agent markdown loading
├── Dockerfile
├── railway.toml
├── requirements.txt
└── .env.example
```

---

## Troubleshooting

**Bot not responding**
```bash
tail -100 logs/bot.log
```

**Voice transcribing in wrong language**
Set `WHISPER_LANGUAGE=en` in `.env`. Whisper auto-detect can misidentify accented English (e.g. Singapore/Malaysian English may be detected as Malay).

**Voice reply not appearing as a voice bubble in Telegram**
Ensure `OPENAI_API_KEY` is set. The bot uses OpenAI TTS with `response_format="opus"` which produces OGG/Opus — the format Telegram requires for voice bubbles.

**Group chat: bot not responding to @mention**
Disable Group Privacy in BotFather: `/mybots` → your bot → Bot Settings → Group Privacy → **Turn off**. Then remove and re-add the bot to the group.

**Data lost after Railway redeploy**
Add a PostgreSQL addon and set `DATABASE_URL` to the Postgres connection string. SQLite on Railway uses ephemeral storage.

**Agent behaviour not updating**
Edit `SOUL.md`, `RULES.md`, or `SKILLS.md`, then send `/reload` in Telegram — no restart needed.
