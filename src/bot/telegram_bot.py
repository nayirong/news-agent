"""
Telegram bot: command handlers, message routing, and main entry point.

Features:
  - Privacy: only users listed in ALLOWED_USER_IDS can interact with the bot.
  - Group chats: responds only when @mentioned or when someone replies to the bot.
  - Voice messages: transcribes via Whisper, replies with both text and audio.
  - Commands: /start /help /digest /interests /settime /reload

Messages:
    Comma-separated text  → save interests + generate digest
    Any other text        → web-search Q&A
    Voice message         → transcribe → route same as text, reply with audio
"""
import logging
import os

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config.settings import settings
from src.ai.claude_client import claude_client
from src.ai.agent_tools import AgentToolExecutor
from src.user.profile_manager import profile_manager
from src.scheduler.news_scheduler import NewsScheduler
from src.database.db_manager import db_manager

logger = logging.getLogger(__name__)

# Global scheduler reference so command handlers can reschedule users
_scheduler: NewsScheduler = None


# ---------------------------------------------------------------------------
# Auth & group helpers
# ---------------------------------------------------------------------------

def is_authorized(user_id: int) -> bool:
    """Return True if the user is allowed to use the bot.

    If ALLOWED_USER_IDS is empty (not configured), everyone is allowed.
    """
    return not settings.ALLOWED_USER_IDS or user_id in settings.ALLOWED_USER_IDS


async def _reject_if_unauthorized(update: Update) -> bool:
    """Check auth; send a private rejection if needed. Returns True when blocked."""
    if is_authorized(update.effective_user.id):
        return False
    # Only reply in private chats — silently ignore in groups to avoid spam
    if update.message and update.message.chat.type == "private":
        await update.message.reply_text("This bot is private. 🔒")
    return True


def _is_for_bot(update: Update, bot_id: int, bot_username: str) -> bool:
    """Decide whether the bot should respond to this group message.

    In private chats: always True.
    In groups/supergroups: True only if the message @mentions the bot or is a
    direct reply to one of the bot's messages.
    """
    msg = update.message
    if msg.chat.type == "private":
        return True

    # @mention in text entities
    text = msg.text or msg.caption or ""
    if msg.entities:
        for entity in msg.entities:
            if entity.type == "mention":
                mention = text[entity.offset : entity.offset + entity.length]
                if mention.lower() == f"@{bot_username.lower()}":
                    return True

    # Reply to a message sent by the bot
    if msg.reply_to_message and msg.reply_to_message.from_user:
        if msg.reply_to_message.from_user.id == bot_id:
            return True

    return False


def _strip_mention(text: str, bot_username: str) -> str:
    """Remove @botname from message text and clean up whitespace."""
    cleaned = text.replace(f"@{bot_username}", "").replace(f"@{bot_username.lower()}", "")
    return " ".join(cleaned.split())


# ---------------------------------------------------------------------------
# Core message processor (shared by text and voice handlers)
# ---------------------------------------------------------------------------

async def _process_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    voice_reply: bool = False,
) -> None:
    """Route a (possibly transcribed) message and generate a response.

    Args:
        text: The message text to process (already stripped of @mention).
        voice_reply: If True, also send an audio version of Q&A answers.
    """
    tg_user = update.effective_user
    user = profile_manager.get_or_create_user(
        telegram_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
    )
    user_id = user["user_id"]

    if profile_manager.looks_like_interest_list(text):
        # --- Setting interests ---
        interests = profile_manager.set_interests_from_text(user_id, text)

        if not interests:
            await update.message.reply_text(
                "I couldn't parse that as a list of topics.\n"
                "Please use comma-separated topics, e.g.:\n"
                "AI, climate tech, NBA, startup funding"
            )
            return

        await update.message.reply_text(
            f"Interests saved: {', '.join(interests)}\n\n"
            "Searching the web for your first digest now..."
        )

        digest = claude_client.generate_digest(interests)

        await update.message.reply_text(
            f"📰 *Your News Digest*\n\n{digest}",
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )

        if _scheduler:
            _scheduler.reschedule_user(
                user_id=user_id,
                telegram_id=tg_user.id,
                interests=interests,
                delivery_time=user["delivery_time"],
            )

    else:
        # --- Answering a question ---
        recent_convos = db_manager.get_recent_conversations(user_id, limit=3)
        context_parts = []
        for c in recent_convos:
            if c.get("response"):
                preview = c["response"][:300].replace("\n", " ")
                context_parts.append(f"Q: {c['message']}\nA: {preview}...")

        # Inject the user's actual profile so Claude can answer questions about
        # schedule, interests, and digest destination accurately.
        interests_now = profile_manager.get_interests(user_id)
        digest_dest = (
            f"group chat (chat_id={user['digest_chat_id']})"
            if user.get("digest_chat_id")
            else "private DM"
        )
        profile_note = (
            f"[User profile — delivery_time: {user['delivery_time']} UTC, "
            f"digest_destination: {digest_dest}, "
            f"interests: {', '.join(interests_now) if interests_now else 'none set'}]"
        )
        context_parts.insert(0, profile_note)
        recent_context = "\n\n".join(context_parts)

        await update.message.reply_text("On it...")

        executor = AgentToolExecutor(
            user_id=user_id,
            telegram_id=tg_user.id,
            db_manager=db_manager,
            scheduler=_scheduler,
        )

        answer = claude_client.answer_question(
            question=text,
            recent_context=recent_context,
            tool_executor=executor,
        )

        executor.reschedule_if_needed(user)

        await update.message.reply_text(
            answer,
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )

        # Optionally send an audio version of the answer
        if voice_reply:
            try:
                from src.bot.voice_handler import text_to_voice_opus
                audio_buf = await text_to_voice_opus(answer)
                await context.bot.send_voice(
                    chat_id=update.effective_chat.id,
                    voice=audio_buf,
                )
            except Exception as e:
                logger.warning(f"Voice reply failed (text already sent): {e}")

        db_manager.save_conversation(user_id, message=text, response=answer)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start — Onboard new users or greet returning users."""
    if await _reject_if_unauthorized(update):
        return

    tg_user = update.effective_user
    user = profile_manager.get_or_create_user(
        telegram_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
    )

    if profile_manager.has_interests(user["user_id"]):
        interests = profile_manager.get_interests(user["user_id"])
        await update.message.reply_text(
            f"Welcome back! Your current interests: {', '.join(interests)}\n\n"
            "Use /digest for an on-demand digest, or just ask me anything.\n"
            "Send a new comma-separated list to update your interests."
        )
    else:
        await update.message.reply_text(
            "Welcome to Atlas, your AI news assistant.\n\n"
            "I search the web in real-time to deliver personalized news "
            "summaries tailored to your interests.\n\n"
            "To get started, tell me what topics you care about.\n"
            "Example: AI, climate tech, NBA, startup funding\n\n"
            "Just type them as a comma-separated list."
        )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/help — Display available commands and usage."""
    if await _reject_if_unauthorized(update):
        return

    voice_status = "enabled" if settings.OPENAI_API_KEY else "disabled (set OPENAI_API_KEY)"
    await update.message.reply_text(
        "Atlas — AI News Assistant\n\n"
        "Commands:\n"
        "/start           — Welcome and setup\n"
        "/help            — This message\n"
        "/digest          — Get a digest right now\n"
        "/interests       — View your current interests\n"
        "/settime HH:MM   — Change daily digest time (UTC)\n"
        "/digesthere      — Deliver daily digests to this chat\n"
        "/reload          — Reload agent configuration\n\n"
        "Just send a message to:\n"
        "• Set interests: AI, NBA, climate tech\n"
        "• Ask a question: What happened in AI today?\n"
        "• Request a topic: What's the latest on OpenAI?\n"
        "• Send a voice message to speak your question\n\n"
        f"Voice: {voice_status}"
    )


async def cmd_digest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/digest — Generate and deliver an on-demand digest immediately."""
    if await _reject_if_unauthorized(update):
        return

    tg_user = update.effective_user
    user = profile_manager.get_or_create_user(telegram_id=tg_user.id)
    interests = profile_manager.get_interests(user["user_id"])

    if not interests:
        await update.message.reply_text(
            "You haven't set any interests yet.\n"
            "Send me a comma-separated list of topics, e.g.:\n"
            "AI, climate tech, NBA, startup funding"
        )
        return

    await update.message.reply_text("Searching the web for your latest news...")

    digest = claude_client.generate_digest(interests)

    await update.message.reply_text(
        f"📰 *Your News Digest*\n\n{digest}",
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


async def cmd_interests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/interests — Show the user's current interest list."""
    if await _reject_if_unauthorized(update):
        return

    tg_user = update.effective_user
    user = profile_manager.get_or_create_user(telegram_id=tg_user.id)
    interests = profile_manager.get_interests(user["user_id"])

    if not interests:
        await update.message.reply_text(
            "You have no interests set yet.\n"
            "Send a comma-separated list to get started:\n"
            "AI, climate tech, NBA"
        )
    else:
        interest_lines = "\n".join(f"• {i}" for i in interests)
        await update.message.reply_text(
            f"Your current interests:\n\n{interest_lines}\n\n"
            "Send a new comma-separated list to replace them."
        )


async def cmd_settime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/settime HH:MM — Set the daily digest delivery time (UTC)."""
    if await _reject_if_unauthorized(update):
        return

    tg_user = update.effective_user
    user = profile_manager.get_or_create_user(telegram_id=tg_user.id)

    if not context.args:
        await update.message.reply_text(
            "Usage: /settime HH:MM\n"
            "Example: /settime 07:30\n"
            "Times are in UTC."
        )
        return

    time_str = context.args[0]
    success = profile_manager.update_delivery_time(user["user_id"], time_str)

    if not success:
        await update.message.reply_text(
            "Invalid format. Use HH:MM (24-hour).\n"
            "Example: /settime 07:30"
        )
        return

    if _scheduler:
        interests = profile_manager.get_interests(user["user_id"])
        if interests:
            _scheduler.reschedule_user(
                user_id=user["user_id"],
                telegram_id=tg_user.id,
                interests=interests,
                delivery_time=time_str,
            )

    await update.message.reply_text(f"Daily digest time updated to {time_str} UTC.")


async def cmd_reload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/reload — Force-reload the agent definition from markdown files."""
    if await _reject_if_unauthorized(update):
        return

    from src.agent_loader import agent_loader
    agent_loader.reload_agent(settings.DEFAULT_AGENT_NAME)
    await update.message.reply_text(
        f"Agent '{settings.DEFAULT_AGENT_NAME}' reloaded from markdown files.\n"
        "Changes to SOUL.md, RULES.md, and SKILLS.md are now active."
    )


async def cmd_digesthere(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/digesthere — Deliver scheduled digests to this chat (group or DM).

    Run in a group to redirect digests there.
    Run in a private DM to reset delivery back to your DM.
    """
    if await _reject_if_unauthorized(update):
        return

    tg_user = update.effective_user
    chat = update.effective_chat
    user = profile_manager.get_or_create_user(telegram_id=tg_user.id)
    user_id = user["user_id"]

    if chat.type == "private":
        # Reset to private DM
        db_manager.update_digest_chat(user_id, None)
        await update.message.reply_text(
            "Daily digests will now be delivered to this private chat."
        )
        new_digest_chat_id = None
    else:
        # Set this group as the digest destination
        db_manager.update_digest_chat(user_id, chat.id)
        await update.message.reply_text(
            f"Daily digests will now be delivered to *{chat.title or 'this group'}*.",
            parse_mode="Markdown",
        )
        new_digest_chat_id = chat.id

    # Reschedule with the new destination
    if _scheduler:
        interests = profile_manager.get_interests(user_id)
        if interests:
            _scheduler.reschedule_user(
                user_id=user_id,
                telegram_id=tg_user.id,
                interests=interests,
                delivery_time=user["delivery_time"],
                digest_chat_id=new_digest_chat_id,
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

    await _process_message(update, context, text, voice_reply=False)


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
        logger.error(f"Voice transcription failed: {e}", exc_info=True)
        await update.message.reply_text(
            "Sorry, I couldn't transcribe your voice message. Please try again or type your question."
        )
        return

    # Echo back what was heard so the user can confirm
    await update.message.reply_text(
        f'🎤 _I heard: "{transcribed}"_',
        parse_mode="Markdown",
    )

    if not transcribed:
        return

    await _process_message(update, context, transcribed, voice_reply=True)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Build and start the Telegram bot.

    Initialization order:
    1. Create logs directory
    2. Initialize database tables
    3. Validate required settings
    4. Build Telegram Application
    5. Register handlers
    6. Start the news scheduler
    7. Start polling
    8. Stop scheduler on exit
    """
    global _scheduler

    os.makedirs("logs", exist_ok=True)

    file_handler = logging.FileHandler(settings.LOG_FILE)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logging.getLogger().addHandler(file_handler)

    db_manager.init_db()

    if not settings.TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set. Check your .env file.")
    if not settings.ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY is not set. Check your .env file.")

    if settings.ALLOWED_USER_IDS:
        logger.info(f"Privacy mode: bot restricted to user IDs {settings.ALLOWED_USER_IDS}")
    else:
        logger.warning("Privacy mode: ALLOWED_USER_IDS is empty — bot is open to everyone.")

    if settings.OPENAI_API_KEY:
        logger.info("Voice support: enabled (Whisper + gTTS)")
    else:
        logger.info("Voice support: disabled (OPENAI_API_KEY not set)")

    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("digest", cmd_digest))
    app.add_handler(CommandHandler("interests", cmd_interests))
    app.add_handler(CommandHandler("settime", cmd_settime))
    app.add_handler(CommandHandler("digesthere", cmd_digesthere))
    app.add_handler(CommandHandler("reload", cmd_reload))

    # Text messages (not commands)
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
    )

    # Voice messages
    app.add_handler(
        MessageHandler(filters.VOICE, handle_voice_message)
    )

    _scheduler = NewsScheduler(bot=app.bot)
    _scheduler.start()

    logger.info(
        f"Atlas News Agent starting — "
        f"model={settings.CLAUDE_MODEL}, "
        f"agent='{settings.DEFAULT_AGENT_NAME}'"
    )

    app.run_polling(drop_pending_updates=True)

    _scheduler.stop()
    logger.info("Atlas News Agent stopped cleanly")
