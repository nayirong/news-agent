# Atlas & Aria — AI Telegram Bots

Two personal Telegram bots powered by Claude:
- **Atlas** — delivers AI-curated news digests and answers questions in real time using web search
- **Aria** — a calendar secretary that reads and writes your Google Calendar, supports voice and image input

---

## Changelog

| Version | Date | Summary |
|---|---|---|
| 1.2.0 | 2026-03-06 | Fix calendar timezone handling; narrow Atlas news search to T-1 |
| 1.1.0 | 2026-03-01 | Add Aria calendar secretary bot (Google Calendar, vision support, multi-bot runner) |
| 1.0.0 | 2025-02-01 | Initial release: Atlas news agent with Claude Haiku + web search + voice |

---

## Atlas — News Agent

Tell it your interests, pick a delivery time, and get a concise briefing every day — by text or voice.

### Features

- **Personalized digests** — set topics like `AI, climate tech, NBA` and get 5–7 stories each day
- **Real-time web search** — every answer is sourced live (T-1, never from stale memory)
- **Daily scheduling** — digest delivered at your chosen time, survives restarts
- **Follow-up Q&A** — ask anything; the bot searches and replies with cited sources
- **Voice messages** — send a voice note, get a voice reply (optional, requires OpenAI key)
- **Group chat support** — add to a group; bot responds only when @mentioned or replied-to
- **Privacy controls** — restrict access to specific Telegram user IDs
- **Agent-driven behaviour** — personality, rules, and skills defined in plain markdown files

### Bot Commands

| Command | Description |
|---|---|
| `/start` | Onboard or greet returning users |
| `/help` | Show available commands and voice status |
| `/digest` | Generate an on-demand digest immediately |
| `/interests` | View your current interest list |
| `/settime HH:MM` | Change your daily digest time (UTC) |
| `/digesthere` | Send future digests to this chat (useful for groups) |
| `/reload` | Hot-reload agent markdown files without restarting |

**Setting interests:** Send a comma-separated message like `AI, Formula 1, geopolitics` — the bot detects it and sets your interests automatically.

---

## Aria — Calendar Secretary

A calendar-aware assistant that reads and writes your Google Calendar. Send text, voice, or a screenshot of an event invite — Aria handles the rest.

### Features

- **Upcoming events** — ask what's on your schedule today or this week
- **Conflict detection** — always checks for overlaps before creating an event
- **Event creation & deletion** — confirms with you before making any changes
- **Time insights** — how many hours did you spend in meetings this week?
- **Vision support** — send a screenshot of an invite; Aria extracts and books it
- **Voice support** — send voice notes, get voice replies (requires OpenAI key)
- **Timezone-aware** — all times stored and displayed in your configured local timezone

### Calendar Tools

| Tool | Description |
|---|---|
| `get_upcoming_events` | List events for the next N days |
| `check_conflicts` | Find overlapping events for a proposed time slot |
| `create_event` | Add a new event (requires user confirmation) |
| `delete_event` | Remove an event by ID (requires user confirmation) |
| `get_time_insights` | Meeting-hours statistics for the past N days |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Bot framework | `python-telegram-bot` 20.7 (async) |
| AI + web search | Anthropic Claude Haiku + `web_search_20250305` |
| Calendar | Google Calendar API v3 (service account) |
| Voice transcription | OpenAI Whisper (`whisper-1`) |
| Voice synthesis | OpenAI TTS (`tts-1`, OGG/Opus) |
| Scheduler | APScheduler 3.10 (AsyncIOScheduler) |
| Database | SQLAlchemy 2.0 — SQLite (local) or PostgreSQL (production) |
| Deployment | Docker + Railway |

---

## Prerequisites

- Python 3.11+
- Two Telegram bot tokens from [@BotFather](https://t.me/BotFather) (one per bot)
- An [Anthropic API key](https://console.anthropic.com) (required)
- An [OpenAI API key](https://platform.openai.com) (optional — enables voice)
- A Google Cloud service account with Calendar API enabled (required for Aria)

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
# Atlas
TELEGRAM_BOT_TOKEN=your_atlas_token

# Aria
TELEGRAM_BOT_TOKEN_SECRETARY=your_aria_token

# Shared
ANTHROPIC_API_KEY=your_key_here
ALLOWED_USER_IDS=your_telegram_id   # find yours via @userinfobot

# Google Calendar (Aria)
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account",...}
GOOGLE_CALENDAR_ID=you@gmail.com
GOOGLE_CALENDAR_TIMEZONE=Asia/Singapore
```

**3. Initialise the database**

```bash
python scripts/setup_db.py
```

**4. Start the bots**

```bash
# Both bots (production)
python scripts/run_all.py

# Atlas only
python scripts/run_bot.py

# Aria only
python scripts/run_secretary.py
```

---

## Configuration

All settings are read from environment variables. See `.env.example` for the full list.

### Required

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Atlas bot token from `@BotFather` |
| `TELEGRAM_BOT_TOKEN_SECRETARY` | Aria bot token from `@BotFather` |
| `ANTHROPIC_API_KEY` | From [console.anthropic.com](https://console.anthropic.com) |

### Google Calendar (Aria)

| Variable | Default | Description |
|---|---|---|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | *(required)* | Full JSON string of your service account key |
| `GOOGLE_CALENDAR_ID` | `primary` | Your Gmail address or calendar ID |
| `GOOGLE_CALENDAR_TIMEZONE` | `UTC` | IANA timezone (e.g. `Asia/Singapore`) — **set this!** |

### Privacy

| Variable | Default | Description |
|---|---|---|
| `ALLOWED_USER_IDS` | *(empty — open to all)* | Comma-separated Telegram user IDs |

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

## Google Calendar Setup (Aria)

1. **Google Cloud Console** → Create project → Enable **Google Calendar API**
2. **IAM & Admin** → Service Accounts → Create service account → Download JSON key
3. **Share your Google Calendar** with the service account email address (give it Editor access)
4. Set `GOOGLE_SERVICE_ACCOUNT_JSON` to the full JSON string (or path to the key file)
5. Set `GOOGLE_CALENDAR_ID` to your Gmail address
6. Set `GOOGLE_CALENDAR_TIMEZONE` to your IANA timezone (e.g. `Asia/Singapore`)

---

## Agent Behaviour

Bot personalities and rules live in plain markdown — no code changes needed:

| File | Purpose |
|---|---|
| `0. Agents/News Agent/SOUL.md` | Atlas personality & values |
| `0. Agents/News Agent/RULES.md` | Atlas hard constraints |
| `0. Agents/News Agent/SKILLS.md` | Atlas capabilities & output formats |
| `0. Agents/Calendar Agent/SOUL.md` | Aria personality & values |
| `0. Agents/Calendar Agent/RULES.md` | Aria hard constraints |
| `0. Agents/Calendar Agent/SKILLS.md` | Aria calendar capabilities |

Edit any of these files and send `/reload` in Telegram to apply changes instantly (Atlas). Aria picks up changes on next restart.

---

## Railway Deployment

The repo ships with a `Dockerfile` and `railway.toml` ready for one-click deployment. The default start command runs **both bots** via `scripts/run_all.py`.

**1. Push to GitHub** (`.gitignore` already excludes `.env` and `*.db`)

**2. Create a new project at [railway.app](https://railway.app)** and connect your repo to the **`master`** branch (not `main`)

**3. Add environment variables** in the Railway dashboard (use `.env.example` as reference)

**4. Add a PostgreSQL addon** for persistent storage — without it, SQLite data is lost on every redeploy. Set `DATABASE_URL` to the provided connection string.

Railway restarts the container automatically on failure (up to 10 retries, per `railway.toml`).

### Running a single bot on Railway

Set the `START_MODE` environment variable:

| Value | Behaviour |
|---|---|
| `all` | Start both Atlas and Aria (default) |
| `atlas` | Start Atlas only |
| `secretary` | Start Aria only |

---

## Group Chat Setup (Atlas)

1. Add the bot to your Telegram group
2. In BotFather: `/mybots` → your bot → Bot Settings → Group Privacy → **Turn off**
3. Remove and re-add the bot to the group
4. The bot responds only when **@mentioned** or when someone **replies to a bot message**

---

## Project Structure

```
news-agent/
├── 0. Agents/
│   ├── News Agent/
│   │   ├── SOUL.md              Atlas personality & values
│   │   ├── RULES.md             Atlas hard constraints
│   │   └── SKILLS.md            Atlas capabilities
│   └── Calendar Agent/
│       ├── SOUL.md              Aria personality & values
│       ├── RULES.md             Aria hard constraints
│       └── SKILLS.md            Aria calendar capabilities
├── config/
│   └── settings.py              All configuration from environment variables
├── src/
│   ├── agent_loader.py          Reads markdown files → assembles system prompt
│   ├── ai/
│   │   ├── claude_client.py     Atlas: Claude API wrapper + web search agentic loop
│   │   ├── secretary_client.py  Aria: Claude API wrapper + calendar tools + vision
│   │   └── agent_tools.py       Atlas tools (interests, schedule management)
│   ├── bot/
│   │   ├── telegram_bot.py      Atlas command handlers, message routing
│   │   ├── secretary_bot.py     Aria command handlers, vision + voice routing
│   │   └── voice_handler.py     Whisper transcription + OpenAI TTS
│   ├── calendar/
│   │   ├── gcal_client.py       Google Calendar API v3 wrapper (service account)
│   │   └── calendar_tools.py    Tool schemas + executor for Claude calendar calls
│   ├── database/
│   │   ├── models.py            SQLAlchemy ORM (User, UserInterest, Conversation)
│   │   └── db_manager.py        DB operations singleton
│   ├── scheduler/
│   │   └── news_scheduler.py    APScheduler — daily digest jobs
│   └── user/
│       └── profile_manager.py   User profile facade (interests, delivery time)
├── scripts/
│   ├── run_all.py               Start both Atlas and Aria (production entry point)
│   ├── run_bot.py               Start Atlas only
│   ├── run_secretary.py         Start Aria only
│   ├── setup_db.py              One-time DB initialisation
│   ├── test_agent_loader.py     Smoke test for agent markdown loading
│   └── test_calendar.py         Smoke test for Google Calendar connection
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

**Calendar events showing at wrong time**
Ensure `GOOGLE_CALENDAR_TIMEZONE` is set to your IANA timezone (e.g. `Asia/Singapore`). If unset, the default is `UTC` which will shift all event times by your UTC offset.

**Voice transcribing in wrong language**
Set `WHISPER_LANGUAGE=en` in `.env`. Whisper auto-detect can misidentify accented English (e.g. Singapore/Malaysian English may be detected as Malay).

**Voice reply not appearing as a voice bubble in Telegram**
Ensure `OPENAI_API_KEY` is set. The bot uses OpenAI TTS with `response_format="opus"` which produces OGG/Opus — the format Telegram requires for voice bubbles.

**Group chat: bot not responding to @mention**
Disable Group Privacy in BotFather: `/mybots` → your bot → Bot Settings → Group Privacy → **Turn off**. Then remove and re-add the bot to the group.

**Data lost after Railway redeploy**
Add a PostgreSQL addon and set `DATABASE_URL` to the Postgres connection string. SQLite on Railway uses ephemeral storage.

**Railway not auto-deploying on push**
In Railway: Service → Settings → Source — verify the repo is connected and the branch is set to `master` (not `main`). Ensure Auto Deploy is toggled on.

**Agent behaviour not updating**
Edit `SOUL.md`, `RULES.md`, or `SKILLS.md`, then send `/reload` in Telegram (Atlas). For Aria, restart the bot to pick up changes.
