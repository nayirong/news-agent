import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

    # Privacy — comma-separated Telegram user IDs allowed to use this bot.
    # Leave empty to allow everyone (not recommended for personal bots).
    # Example: ALLOWED_USER_IDS=123456789,987654321
    ALLOWED_USER_IDS: set = {
        int(x.strip())
        for x in os.getenv("ALLOWED_USER_IDS", "").split(",")
        if x.strip().isdigit()
    }

    # Anthropic
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

    # OpenAI — required for voice transcription (Whisper) and TTS replies.
    # Voice features are silently disabled if this is not set.
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Whisper language hint — ISO 639-1 code (e.g. "en", "ms", "zh").
    # Prevents Whisper from misdetecting accented English as another language.
    # Leave empty for full auto-detect.
    WHISPER_LANGUAGE: str = os.getenv("WHISPER_LANGUAGE", "en")

    # OpenAI TTS voice — options: alloy, echo, fable, onyx, nova, shimmer
    # nova: warm, professional female. onyx: deep, authoritative male.
    VOICE_NAME: str = os.getenv("VOICE_NAME", "nova")

    # Claude model (haiku for cost efficiency)
    CLAUDE_MODEL: str = "claude-haiku-4-5-20251001"

    # Web search tool specification
    WEB_SEARCH_TOOL: dict = {
        "type": "web_search_20250305",
        "name": "web_search"
    }

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///news_agent.db")

    # Scheduler defaults
    DEFAULT_DELIVERY_TIME: str = os.getenv("DEFAULT_DELIVERY_TIME", "08:00")
    DEFAULT_TIMEZONE: str = os.getenv("DEFAULT_TIMEZONE", "UTC")

    # Agent system — paths are relative to the project root (where run_bot.py is started from)
    AGENTS_DIR: str = os.getenv("AGENTS_DIR", "0. Agents")
    DEFAULT_AGENT_NAME: str = "News Agent"

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "logs/bot.log")

    # Token limits per call type
    MAX_TOKENS_DIGEST: int = 3000
    MAX_TOKENS_FOLLOWUP: int = 1500
    MAX_TOKENS_ONDEMAND: int = 1500


settings = Settings()
