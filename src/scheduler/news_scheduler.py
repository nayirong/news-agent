"""
NewsScheduler: sends daily digests to all users at their preferred time.

Uses APScheduler's AsyncIOScheduler so it runs inside the same asyncio event
loop as the Telegram bot (python-telegram-bot v20 is fully async).

Usage:
    scheduler = NewsScheduler(bot=app.bot)
    scheduler.start()   # loads all users from DB and schedules jobs
    # ... bot runs ...
    scheduler.stop()    # graceful shutdown
"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.ai.claude_client import claude_client
from src.database.db_manager import db_manager

logger = logging.getLogger(__name__)


class NewsScheduler:
    """
    Manages scheduled delivery of daily news digests.

    Each user gets one APScheduler CronTrigger job, keyed by their user_id.
    Jobs are loaded from the database on startup and can be updated at runtime
    when users change their delivery time or interests.
    """

    def __init__(self, bot):
        """
        Args:
            bot: The Telegram Bot instance from python-telegram-bot Application.
                 Used to send messages to users.
        """
        self.bot = bot
        self.scheduler = AsyncIOScheduler()

    async def _send_digest_to_user(
        self,
        user_id: int,
        telegram_id: int,
        interests: list[str],
        digest_chat_id: int = None,
    ) -> None:
        """
        APScheduler job function: generate and send one user's daily digest.

        Sends to digest_chat_id (a group) if configured, otherwise to the
        user's private DM (telegram_id).

        Catches all exceptions so one user's failure does not affect
        other scheduled jobs. Sends a brief error notification if delivery fails.
        """
        send_to = digest_chat_id or telegram_id
        try:
            logger.info(f"Scheduled digest triggered for user_id={user_id} → chat_id={send_to}")

            digest = claude_client.generate_digest(interests)

            message = f"📰 *Your Daily News Digest*\n\n{digest}"

            await self.bot.send_message(
                chat_id=send_to,
                text=message,
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )

            logger.info(f"Daily digest delivered to user_id={user_id} → chat_id={send_to}")

        except Exception as e:
            logger.error(f"Failed to send digest to user_id={user_id}: {e}")
            try:
                await self.bot.send_message(
                    chat_id=telegram_id,  # always fall back to private DM for errors
                    text=(
                        "Sorry, I couldn't generate your digest this morning. "
                        "I'll try again tomorrow! You can also use /digest anytime."
                    ),
                )
            except Exception as notify_err:
                logger.error(
                    f"Could not send error notification to user_id={user_id}: {notify_err}"
                )

    def schedule_user(
        self,
        user_id: int,
        telegram_id: int,
        interests: list[str],
        delivery_time: str,
        timezone: str = "UTC",
        digest_chat_id: int = None,
    ) -> None:
        """
        Add or replace the scheduled digest job for one user.

        Args:
            user_id: Internal database user ID.
            telegram_id: Telegram chat ID to send the message to.
            interests: List of interest strings for the digest.
            delivery_time: HH:MM format string (e.g., "08:00").
            timezone: IANA timezone string (e.g., "America/New_York"). Defaults to UTC.
        """
        try:
            hour, minute = map(int, delivery_time.split(":"))
        except (ValueError, AttributeError):
            logger.error(
                f"Invalid delivery_time '{delivery_time}' for user_id={user_id}. "
                "Defaulting to 08:00 UTC."
            )
            hour, minute = 8, 0

        job_id = f"digest_{user_id}"

        self.scheduler.add_job(
            self._send_digest_to_user,
            trigger=CronTrigger(hour=hour, minute=minute, timezone=timezone),
            args=[user_id, telegram_id, interests, digest_chat_id],
            id=job_id,
            replace_existing=True,
            misfire_grace_time=300,  # 5-minute grace window if job fires late
        )

        logger.info(
            f"Scheduled digest for user_id={user_id} "
            f"at {delivery_time} {timezone} (job_id={job_id})"
        )

    def reschedule_user(
        self,
        user_id: int,
        telegram_id: int,
        interests: list[str],
        delivery_time: str,
        timezone: str = "UTC",
        digest_chat_id: int = None,
    ) -> None:
        """
        Public method to update a user's scheduled job.

        Called when the user changes their delivery time (/settime),
        updates their interests, or changes their digest destination (/digesthere).
        """
        self.schedule_user(user_id, telegram_id, interests, delivery_time, timezone, digest_chat_id)

    def unschedule_user(self, user_id: int) -> None:
        """
        Remove the scheduled job for a user.

        Called if a user unsubscribes or deletes their account.
        """
        job_id = f"digest_{user_id}"
        job = self.scheduler.get_job(job_id)
        if job:
            job.remove()
            logger.info(f"Unscheduled digest for user_id={user_id}")

    def load_all_users(self) -> None:
        """
        Load all users with interests from the database and schedule their digests.

        Called once on startup to restore all scheduled jobs.
        """
        users = db_manager.get_all_users_with_preferences()
        count = 0

        for user in users:
            self.schedule_user(
                user_id=user["user_id"],
                telegram_id=user["telegram_id"],
                interests=user["interests"],
                delivery_time=user["delivery_time"],
                timezone=user.get("timezone", "UTC"),
                digest_chat_id=user.get("digest_chat_id"),
            )
            count += 1

        logger.info(f"Loaded and scheduled {count} user digest(s)")

    def start(self) -> None:
        """Load all users from DB, then start the scheduler."""
        self.load_all_users()
        self.scheduler.start()
        logger.info("NewsScheduler started")

    def stop(self) -> None:
        """Gracefully shut down the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("NewsScheduler stopped")
