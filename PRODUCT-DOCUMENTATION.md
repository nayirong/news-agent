# Atlas — AI News Agent
### Product Documentation

---

## Changelog

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | Feb 2026 | Initial concept — news fetcher approach (not built) |
| v2.0 | Feb 2026 | Pivoted to Claude web_search approach. Core bot, scheduler, SQLite DB |
| v2.1 | Feb 2026 | Agent system (SOUL / RULES / SKILLS markdown files). Conversation context |
| v2.2 | Mar 2026 | **Voice messages** (Whisper + OpenAI TTS), **group chat** support, **privacy whitelist**, **Railway deployment** (Dockerfile), OpenAI TTS replacing gTTS, markdown stripping for TTS |

---

## Overview

Atlas is a personal AI news agent delivered through Telegram. It searches the web in real-time using Claude's `web_search` tool and delivers personalized news digests and Q&A responses — by text or voice.

**Core value proposition:** Replace 30+ minutes of daily news browsing with a concise, AI-curated digest, delivered on your schedule, accessible by text or voice.

---

## Architecture

```
User (Telegram: text or voice)
          │
          ▼
  telegram_bot.py
  ┌─────────────────────────────────────┐
  │  Auth check (ALLOWED_USER_IDS)      │
  │  Group detection (@mention / reply) │
  │  Voice transcription (Whisper)      │
  └──────────┬──────────────────────────┘
             │
     ┌───────┴────────┐
     │                │
     ▼                ▼
profile_manager   claude_client
(interests, DB)   (web search + answers)
     │                │
     ▼                ▼
  db_manager      agent_loader
  (SQLite /     (SOUL + RULES + SKILLS
  PostgreSQL)    → system prompt)
             │
             ▼
     news_scheduler
  (daily digest jobs)
             │
             ▼
      OpenAI TTS
   (voice replies, OGG/Opus)
```

**Key design principle:** No article caching. Claude searches the web in real-time for every request — always current, no RSS parsers, no news APIs.

---

## Features

### 1. Personalized News Digests

- User sends comma-separated interests (e.g. `AI, climate tech, NBA`)
- Bot immediately generates a digest via Claude + web search
- Digest is also delivered daily at a configurable time (UTC)
- 5–7 stories per digest, 2–3 sentences each, with source URLs

### 2. Real-Time Q&A

- Any non-interest message is treated as a question
- Claude searches the web and answers with cited sources
- Recent conversation context (last 3 exchanges) is passed for follow-up coherence

### 3. Voice Messages *(requires `OPENAI_API_KEY`)*

- **Voice input:** User sends a voice message → Whisper transcribes it → processed as text
- **Voice output:** Bot replies with a proper Telegram voice bubble (OGG/Opus via OpenAI TTS)
- The bot echoes back what it heard (`🎤 I heard: "..."`) before responding
- Markdown symbols are stripped before TTS so asterisks, dashes, and URLs are not spoken aloud
- Language hint defaults to `en` to prevent accent-based misdetection (configurable via `WHISPER_LANGUAGE`)
- TTS voice configurable via `VOICE_NAME` (default: `nova`)

### 4. Group Chat Support

- Bot can be added to Telegram groups
- Only responds when **@mentioned** or when someone **replies to a bot message**
- Silently ignores all other group messages (no spam)
- `@botname` mention is stripped from text before processing
- **Required BotFather setup:** `/mybots` → your bot → Bot Settings → Group Privacy → **Turn off**

### 5. Privacy / Access Control

- `ALLOWED_USER_IDS` environment variable restricts the bot to specific Telegram user IDs
- In private chats: unauthorized users get a `"This bot is private. 🔒"` message
- In groups: unauthorized senders are silently ignored
- Leave `ALLOWED_USER_IDS` empty to allow everyone (not recommended for personal bots)
- Find your Telegram ID by messaging `@userinfobot`

### 6. Scheduled Daily Digests

- APScheduler runs one cron job per user inside the same asyncio event loop as the bot
- Default delivery: `08:00 UTC` (configurable per user with `/settime HH:MM`)
- Jobs survive restarts (users are loaded from DB on startup)
- Missed jobs have a 5-minute grace window

### 7. Agent-Driven Behavior

Bot personality and rules are defined in plain markdown — no Python code changes needed:

| File | Purpose |
|------|---------|
| `0. Agents/News Agent/SOUL.md` | Personality, tone, communication style |
| `0. Agents/News Agent/RULES.md` | Hard constraints (always cite sources, never fabricate, etc.) |
| `0. Agents/News Agent/SKILLS.md` | 5 capabilities with triggers, behaviors, output formats |

Assembly order: `SOUL → RULES → SKILLS` (joined with `\n\n`) → Claude system prompt.

Use `/reload` in Telegram to hot-reload without restarting the process.

---

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Onboard new users or greet returning users |
| `/help` | Show available commands and voice status |
| `/digest` | Generate an on-demand digest immediately |
| `/interests` | View current interest list |
| `/settime HH:MM` | Change daily digest time (UTC) |
| `/reload` | Reload agent markdown files (dev tool) |

---

## File Structure

```
News Agent/
├── 0. Agents/
│   └── News Agent/
│       ├── SOUL.md          Agent personality & values
│       ├── RULES.md         Hard constraints
│       └── SKILLS.md        5 capabilities with output formats
├── config/
│   ├── __init__.py
│   └── settings.py          All configuration from environment variables
├── src/
│   ├── agent_loader.py      Reads markdown files → assembles system prompt
│   ├── ai/
│   │   └── claude_client.py Claude API wrapper with web search
│   ├── bot/
│   │   ├── telegram_bot.py  Command handlers, message routing, main entry
│   │   └── voice_handler.py Whisper transcription + OpenAI TTS
│   ├── database/
│   │   ├── models.py        SQLAlchemy ORM (User, UserInterest, Conversation)
│   │   └── db_manager.py    DB operations singleton
│   ├── scheduler/
│   │   └── news_scheduler.py APScheduler — daily digest jobs
│   └── user/
│       └── profile_manager.py User profile facade (interests, delivery time)
├── scripts/
│   ├── run_bot.py           Main entry point
│   ├── setup_db.py          One-time DB initialisation
│   └── test_agent_loader.py Smoke test for agent markdown loading
├── Dockerfile               Container definition for Railway / Docker deployment
├── railway.toml             Railway platform config (builder + restart policy)
├── requirements.txt         Python dependencies
├── .env.example             Template for environment variables
└── .gitignore               Excludes .env, *.db, logs/, __pycache__
```

---

## Configuration

All settings are read from environment variables (`.env` file locally, Railway dashboard in production).

### Required

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | From `@BotFather` on Telegram |
| `ANTHROPIC_API_KEY` | From [console.anthropic.com](https://console.anthropic.com) |

### Privacy

| Variable | Default | Description |
|----------|---------|-------------|
| `ALLOWED_USER_IDS` | *(empty — open)* | Comma-separated Telegram user IDs allowed to use the bot |

### Voice *(optional)*

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | *(empty — voice disabled)* | From [platform.openai.com](https://platform.openai.com) |
| `WHISPER_LANGUAGE` | `en` | ISO 639-1 code for transcription. Empty = auto-detect |
| `VOICE_NAME` | `nova` | OpenAI TTS voice: `alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer` |

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///news_agent.db` | SQLite (local) or `postgresql://...` (Railway addon) |

### Scheduler & Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_DELIVERY_TIME` | `08:00` | Default daily digest time (HH:MM UTC) |
| `DEFAULT_TIMEZONE` | `UTC` | IANA timezone for new users |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_FILE` | `logs/bot.log` | Log file path |

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Bot framework | `python-telegram-bot` 20.7 (async) |
| AI — news & Q&A | Anthropic Claude `claude-haiku-4-5-20251001` + `web_search_20250305` |
| Voice transcription | OpenAI Whisper (`whisper-1`) |
| Voice synthesis | OpenAI TTS (`tts-1`, OGG/Opus output) |
| Scheduler | APScheduler 3.10 (AsyncIOScheduler) |
| Database | SQLAlchemy 2.0 — SQLite (local) or PostgreSQL (production) |
| Deployment | Docker + Railway |

---

## Local Setup

```bash
# 1. Install dependencies
pip3 install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env — fill in TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY, ALLOWED_USER_IDS

# 3. Initialize database (first run only)
python3 scripts/setup_db.py

# 4. (Optional) Verify agent files load
python3 scripts/test_agent_loader.py

# 5. Start the bot
python3 scripts/run_bot.py
```

---

## Railway Deployment

Atlas ships with a `Dockerfile` and `railway.toml` for one-command cloud deployment.

```
railway up
```

### Steps

1. Push your repo to GitHub (`.gitignore` already excludes `.env` and `*.db`)
2. Create a new project at [railway.app](https://railway.app) and connect the repo
3. Add environment variables in the Railway dashboard (use `.env.example` as reference)
4. **Persistent database:** Add a **PostgreSQL** addon in Railway and set `DATABASE_URL` to the provided connection string. Without this, SQLite data is lost on every redeploy.

### Dockerfile summary

```
FROM python:3.11-slim
WORKDIR /app
RUN pip install -r requirements.txt
CMD ["python", "scripts/run_bot.py"]
```

Railway restarts the container automatically on failure (up to 10 retries, configured in `railway.toml`).

---

## Database Schema

### `users`
| Column | Type | Notes |
|--------|------|-------|
| `user_id` | Integer PK | Internal ID |
| `telegram_id` | Integer (unique) | Telegram user ID |
| `username` | String | Telegram @handle |
| `first_name` | String | |
| `created_at` | DateTime | |
| `last_active` | DateTime | |
| `timezone` | String | IANA timezone |
| `delivery_time` | String | HH:MM UTC |

### `user_interests`
| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `user_id` | Integer FK | → `users.user_id` |
| `interest` | String | Topic name |
| `weight` | Float | 1.0 default; range [0.1, 5.0] |
| `created_at` | DateTime | |

### `conversations`
| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `user_id` | Integer FK | |
| `message` | Text | User's question |
| `response` | Text | Bot's answer |
| `created_at` | DateTime | |

---

## Cost Estimate (Single User)

| Service | Usage | Monthly Cost |
|---------|-------|-------------|
| Anthropic Claude Haiku | ~30 digests + Q&A | ~$0.50–1.00 |
| OpenAI Whisper | Voice transcription | ~$0.01–0.10 |
| OpenAI TTS | Voice replies | ~$0.05–0.20 |
| Railway (Starter) | Hosting | ~$5.00 |
| **Total** | | **~$6–7 / month** |

---

## Troubleshooting

**Bot not responding**
```bash
tail -100 logs/bot.log
```

**Voice transcribing in wrong language**
Set `WHISPER_LANGUAGE=en` in `.env`. Whisper auto-detect can misidentify accented English as a related language (e.g. Malay for Singapore/Malaysian speakers).

**Voice reply not appearing as a bubble**
Ensure `OPENAI_API_KEY` is set. The bot uses OpenAI TTS with `response_format="opus"` which produces proper OGG/Opus — the format Telegram requires for voice bubbles.

**Group chat: bot not responding to @mention**
Disable Group Privacy in BotFather: `/mybots` → your bot → Bot Settings → Group Privacy → **Turn off**. Then remove and re-add the bot to the group.

**Data lost after Railway redeploy**
Add a PostgreSQL addon to your Railway project and set `DATABASE_URL` to the Postgres connection string. SQLite on Railway uses ephemeral storage.

**Agent behavior not updating**
Edit `SOUL.md`, `RULES.md`, or `SKILLS.md`, then send `/reload` in Telegram — no restart needed.
