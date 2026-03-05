"""
Secretary (Donna) Telegram bot: command handlers, message routing, and app factory.

Features:
  - Privacy: only users listed in ALLOWED_USER_IDS can interact with the bot.
  - Group chats: responds only when @mentioned or when someone replies to the bot.
  - Text messages: routed to Donna for calendar management.
  - Photo messages: image analyzed by Claude vision for event invite extraction.
  - Voice messages: transcribed via Whisper, then processed as text.

Commands:
    /start     — Welcome and setup
    /help      — List commands
    /week      — Show next 7 days of events
    /today     — Show today's events
    /free      — Check free time today
    /insights  — Time management stats for the past week
    /reload    — Hot-reload agent markdown files
"""
import base64
import logging
import os
from io import BytesIO

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config.settings import settings
from src.ai.secretary_client import secretary_client
from src.calendar.gcal_client import gcal_client
from src.calendar.calendar_tools import CalendarToolExecutor
from src.user.profile_manager import profile_manager
from src.database.db_manager import db_manager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Auth & group helpers (mirrors telegram_bot.py)
# ---------------------------------------------------------------------------

def is_authorized(user_id: int) -> bool:
    return not settings.ALLOWED_USER_IDS or user_id in settings.ALLOWED_USER_IDS


async def _reject_if_unauthorized(update: Update) -> bool:
    if is_authorized(update.effective_user.id):
        return False
    if update.message and update.message.chat.type == "private":
        await update.message.reply_text("This bot is private. 🔒")
    return True


def _is_for_bot(update: Update, bot_id: int, bot_username: str) -> bool:
    msg = update.message
    if msg.chat.type == "private":
        return True

    text = msg.text or msg.caption or ""
    # msg.entities covers text messages; msg.caption_entities covers photo/video captions
    entities = list(msg.entities or []) + list(msg.caption_entities or [])
    for entity in entities:
        if entity.type == "mention":
            mention = text[entity.offset: entity.offset + entity.length]
            if mention.lower() == f"@{bot_username.lower()}":
                return True

    if msg.reply_to_message and msg.reply_to_message.from_user:
        if msg.reply_to_message.from_user.id == bot_id:
            return True

    return False


def _strip_mention(text: str, bot_username: str) -> str:
    cleaned = text.replace(f"@{bot_username}", "").replace(f"@{bot_username.lower()}", "")
    return " ".join(cleaned.split())


# ---------------------------------------------------------------------------
# Core message processor
# ---------------------------------------------------------------------------

async def _process_request(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    image_b64: str = None,
    mime_type: str = "image/jpeg",
    voice_reply: bool = False,
) -> None:
    """
    Route a request to Donna (secretary_client) with optional image and calendar tools.

    Fetches the last 5 conversation exchanges from the DB and passes them as
    multi-turn history so Claude can handle short replies like "yes", "confirm",
    or "make it 3pm instead" without losing context.

    Args:
        text:       User's text message (possibly transcribed from voice).
        image_b64:  Base64 image for event invite screenshots (optional).
        mime_type:  MIME type of the image (default: image/jpeg).
        voice_reply: If True, also send an audio version of the answer.
    """
    tg_user = update.effective_user
    user = profile_manager.get_or_create_user(
        telegram_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
    )
    user_id = user["user_id"]

    # Rebuild prior conversation as multi-turn messages for context continuity
    recent_convos = db_manager.get_recent_conversations(user_id, limit=5)
    history = []
    for convo in recent_convos:
        history.append({"role": "user", "content": convo["message"]})
        if convo.get("response"):
            history.append({"role": "assistant", "content": convo["response"]})

    executor = CalendarToolExecutor(gcal_client=gcal_client)

    answer = secretary_client.handle_request(
        text=text,
        image_b64=image_b64,
        mime_type=mime_type,
        tool_executor=executor,
        conversation_history=history,
    )

    await update.message.reply_text(
        answer,
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )

    if voice_reply and settings.OPENAI_API_KEY:
        try:
            from src.bot.voice_handler import text_to_voice_opus
            audio_buf = await text_to_voice_opus(answer)
            await context.bot.send_voice(
                chat_id=update.effective_chat.id,
                voice=audio_buf,
            )
        except Exception as e:
            logger.warning(f"Secretary voice reply failed (text already sent): {e}")

    # Save this exchange so future messages have context
    db_manager.save_conversation(user_id, message=text or "[image]", response=answer)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start — Welcome message."""
    if await _reject_if_unauthorized(update):
        return

    tg_user = update.effective_user
    name = tg_user.first_name or "there"
    await update.message.reply_text(
        f"Hi {name}, I'm Donna — your personal calendar secretary.\n\n"
        "I can:\n"
        "• Show your upcoming events (/week or /today)\n"
        "• Schedule events from text or screenshots\n"
        "• Check for conflicts before booking\n"
        "• Find free time (/free)\n"
        "• Analyze your week (/insights)\n\n"
        "To add an event, just describe it:\n"
        "  \"Schedule a team standup Monday 9–9:30am\"\n\n"
        "Or forward me a screenshot of an invite and I'll extract the details."
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/help — List available commands."""
    if await _reject_if_unauthorized(update):
        return

    voice_status = "enabled" if settings.OPENAI_API_KEY else "disabled (set OPENAI_API_KEY)"
    cal_configured = "configured" if settings.GOOGLE_SERVICE_ACCOUNT_JSON else "NOT configured (set GOOGLE_SERVICE_ACCOUNT_JSON)"

    await update.message.reply_text(
        "Donna — Calendar Secretary\n\n"
        "Commands:\n"
        "/start      — Welcome and setup\n"
        "/help       — This message\n"
        "/week       — Show next 7 days\n"
        "/today      — Show today's events\n"
        "/free       — Check free time today\n"
        "/insights   — Time management stats (past week)\n"
        "/reload     — Reload agent configuration\n\n"
        "Just send a message to:\n"
        "• Ask about your schedule: \"What do I have tomorrow?\"\n"
        "• Schedule something: \"Book a dentist appointment Friday 3pm for 1 hour\"\n"
        "• Send a screenshot of an event invite\n"
        "• Ask for free time: \"Am I free Thursday afternoon?\"\n\n"
        f"Voice: {voice_status}\n"
        f"Calendar: {cal_configured}"
    )


async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/week — Show next 7 days of calendar events."""
    if await _reject_if_unauthorized(update):
        return

    await update.message.reply_text("Checking your calendar...")
    await _process_request(
        update, context,
        text="Show me all my events for the next 7 days.",
    )


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/today — Show today's events."""
    if await _reject_if_unauthorized(update):
        return

    await update.message.reply_text("Checking today...")
    await _process_request(
        update, context,
        text="Show me all my events for today.",
    )


async def cmd_free(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/free — Show free time blocks today."""
    if await _reject_if_unauthorized(update):
        return

    await update.message.reply_text("Checking your free time today...")
    await _process_request(
        update, context,
        text="What free time do I have today? Show me gaps between my scheduled events.",
    )


async def cmd_insights(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/insights — Time management stats for the past week."""
    if await _reject_if_unauthorized(update):
        return

    await update.message.reply_text("Analyzing your past week...")
    await _process_request(
        update, context,
        text="Give me a time management analysis of my past 7 days. How much time did I spend in meetings? What was my busiest day?",
    )


async def cmd_reload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/reload — Force-reload the Calendar Agent from markdown files."""
    if await _reject_if_unauthorized(update):
        return

    from src.agent_loader import agent_loader
    from src.ai.secretary_client import SECRETARY_AGENT_NAME
    agent_loader.reload_agent(SECRETARY_AGENT_NAME)
    await update.message.reply_text(
        "Calendar Agent reloaded from markdown files.\n"
        "Changes to SOUL.md, RULES.md, and SKILLS.md are now active."
    )


# ---------------------------------------------------------------------------
# Message handlers
# ---------------------------------------------------------------------------

async def handle_text_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle free-text messages (non-command)."""
    if await _reject_if_unauthorized(update):
        return

    bot_username = context.bot.username
    bot_id = context.bot.id

    if not _is_for_bot(update, bot_id, bot_username):
        return

    text = _strip_mention(update.message.text.strip(), bot_username)
    if not text:
        return

    await update.message.reply_text("On it...")
    await _process_request(update, context, text=text)


async def handle_photo_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle photo messages — encode image and pass to Donna for event extraction."""
    if await _reject_if_unauthorized(update):
        return

    bot_username = context.bot.username
    bot_id = context.bot.id

    if not _is_for_bot(update, bot_id, bot_username):
        return

    await update.message.reply_text("📸 Analyzing the image...")

    # Download the largest photo variant
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    buf = BytesIO()
    await file.download_to_memory(buf)
    image_bytes = buf.getvalue()
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    # Caption (optional user note alongside the image)
    caption = update.message.caption or ""
    if caption:
        caption = _strip_mention(caption, bot_username)

    await _process_request(
        update, context,
        text=caption,
        image_b64=image_b64,
        mime_type="image/jpeg",
    )


async def handle_voice_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle voice messages — transcribe with Whisper, then process as text."""
    if await _reject_if_unauthorized(update):
        return

    bot_username = context.bot.username
    bot_id = context.bot.id

    if not _is_for_bot(update, bot_id, bot_username):
        return

    if not settings.OPENAI_API_KEY:
        await update.message.reply_text(
            "Voice messages require an OpenAI API key for transcription.\n"
            "Add OPENAI_API_KEY to your environment to enable voice support."
        )
        return

    await update.message.reply_text("🎤 Transcribing...")

    try:
        from src.bot.voice_handler import transcribe_voice
        transcribed = await transcribe_voice(context.bot, update.message.voice.file_id)
    except Exception as e:
        logger.error(f"Secretary voice transcription failed: {e}", exc_info=True)
        await update.message.reply_text(
            "Sorry, I couldn't transcribe your voice message. Please try typing your request."
        )
        return

    await update.message.reply_text(
        f'🎤 _I heard: "{transcribed}"_',
        parse_mode="Markdown",
    )

    if not transcribed:
        return

    await update.message.reply_text("On it...")
    await _process_request(update, context, text=transcribed, voice_reply=True)


# ---------------------------------------------------------------------------
# App factory (used by run_all.py for multi-bot mode)
# ---------------------------------------------------------------------------

def build_app() -> Application:
    """
    Create and configure the Secretary Application without starting it.
    Used by run_all.py to run Atlas and Donna in the same process.
    """
    if not settings.SECRETARY_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN_SECRETARY is not set. Check your .env file.")

    app = Application.builder().token(settings.SECRETARY_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("week", cmd_week))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("free", cmd_free))
    app.add_handler(CommandHandler("insights", cmd_insights))
    app.add_handler(CommandHandler("reload", cmd_reload))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice_message))

    return app


# ---------------------------------------------------------------------------
# Standalone entry point (for run_secretary.py)
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Build and start the Secretary bot standalone.

    Initialization order:
    1. Validate required settings
    2. Build Application
    3. Register handlers
    4. Start polling
    """
    os.makedirs("logs", exist_ok=True)

    file_handler = logging.FileHandler(settings.LOG_FILE)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logging.getLogger().addHandler(file_handler)

    from src.database.db_manager import db_manager
    db_manager.init_db()

    if not settings.ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY is not set. Check your .env file.")

    if not settings.GOOGLE_SERVICE_ACCOUNT_JSON:
        logger.warning(
            "GOOGLE_SERVICE_ACCOUNT_JSON is not set. "
            "Calendar read/write will fail until this is configured."
        )
    if not settings.GOOGLE_CALENDAR_ID:
        logger.warning(
            "GOOGLE_CALENDAR_ID is not set. "
            "Set it to your calendar ID (usually your Gmail address)."
        )

    app = build_app()

    logger.info(
        f"Donna Secretary starting — "
        f"model={settings.CLAUDE_MODEL}, "
        f"agent='Calendar Agent', "
        f"calendar_id={settings.GOOGLE_CALENDAR_ID or '(not set)'}"
    )

    app.run_polling(drop_pending_updates=True)
    logger.info("Donna Secretary stopped cleanly")
