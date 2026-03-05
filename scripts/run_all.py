"""
Run both Atlas (news agent) and Donna (calendar secretary) in the same process.

This is the production entry point used by Railway and Docker.
Both bots share the same event loop, database, and agent loader.

Prerequisites:
    - TELEGRAM_BOT_TOKEN         (Atlas bot from @BotFather)
    - TELEGRAM_BOT_TOKEN_SECRETARY (Donna bot from @BotFather)
    - ANTHROPIC_API_KEY
    - GOOGLE_SERVICE_ACCOUNT_JSON
    - GOOGLE_CALENDAR_ID
    - GOOGLE_CALENDAR_TIMEZONE

Usage:
    python scripts/run_all.py
"""
import asyncio
import logging
import os
import sys

# Resolve project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def run_both() -> None:
    """
    Start Atlas and Donna concurrently in the same asyncio event loop.

    Initialization order:
    1. Create logs dir, init DB
    2. Build both bot Applications
    3. Create and start Atlas scheduler
    4. Start both updaters (polling)
    5. Start both applications (update processing)
    6. Wait until interrupted (Ctrl+C or SIGTERM)
    7. Clean up — stop scheduler, updaters, apps
    """
    os.makedirs("logs", exist_ok=True)

    file_handler = logging.FileHandler("logs/bot.log")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logging.getLogger().addHandler(file_handler)

    from src.database.db_manager import db_manager
    from config.settings import settings

    db_manager.init_db()

    # Validate required settings
    if not settings.TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set.")
    if not settings.SECRETARY_BOT_TOKEN:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN_SECRETARY is not set. "
            "Create a second bot via @BotFather and set this env var."
        )
    if not settings.ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY is not set.")

    if not settings.GOOGLE_SERVICE_ACCOUNT_JSON:
        logger.warning("GOOGLE_SERVICE_ACCOUNT_JSON not set — Donna's calendar tools will fail.")
    if not settings.GOOGLE_CALENDAR_ID:
        logger.warning("GOOGLE_CALENDAR_ID not set — using 'primary' as default.")

    # Build both bot Applications
    from src.bot.telegram_bot import build_app as build_atlas
    from src.bot.secretary_bot import build_app as build_secretary

    atlas_app = build_atlas()
    secretary_app = build_secretary()

    # Wire up Atlas scheduler (uses atlas_app.bot to send messages)
    from src.scheduler.news_scheduler import NewsScheduler
    import src.bot.telegram_bot as atlas_module
    atlas_scheduler = NewsScheduler(bot=atlas_app.bot)
    atlas_module._scheduler = atlas_scheduler  # set module-level global

    logger.info(
        f"Starting Atlas (model={settings.CLAUDE_MODEL}) "
        f"and Donna (calendar agent) in same process..."
    )

    async with atlas_app, secretary_app:
        # Start polling (fetch updates from Telegram)
        await atlas_app.updater.start_polling(drop_pending_updates=True)
        await secretary_app.updater.start_polling(drop_pending_updates=True)

        # Start application (dispatch updates to handlers)
        await atlas_app.start()
        await secretary_app.start()

        # Start scheduler after app is running
        atlas_scheduler.start()

        logger.info("Both Atlas and Donna are running. Press Ctrl+C to stop.")

        try:
            # Block until cancelled
            await asyncio.Event().wait()
        except (asyncio.CancelledError, KeyboardInterrupt):
            logger.info("Shutdown signal received.")

        # Clean shutdown
        atlas_scheduler.stop()
        await atlas_app.updater.stop()
        await secretary_app.updater.stop()
        await atlas_app.stop()
        await secretary_app.stop()

    logger.info("Both bots stopped cleanly.")


if __name__ == "__main__":
    asyncio.run(run_both())
