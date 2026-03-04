"""
Test script: manually fires the scheduled digest job for your user.

Usage:
    python scripts/test_scheduler.py

This bypasses the cron timer and calls _send_digest_to_user() directly,
so you can verify the full delivery pipeline (Claude → Telegram) on demand.
"""
import sys
import os
import asyncio
import logging

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from config.settings import settings
from src.database.db_manager import db_manager


async def main():
    db_manager.init_db()

    users = db_manager.get_all_users_with_preferences()

    if not users:
        print("No users with interests found in the database.")
        print("Send some interests to the bot first (e.g. 'AI, NBA, climate tech').")
        return

    # Show users and let you pick (or just fire for the first one)
    print(f"Found {len(users)} user(s) with interests:\n")
    for i, u in enumerate(users):
        print(f"  [{i}] user_id={u['user_id']}  telegram_id={u['telegram_id']}  "
              f"delivery={u['delivery_time']}  interests={u['interests']}")

    print()
    choice = input("Enter index to fire digest for (default 0): ").strip()
    idx = int(choice) if choice.isdigit() else 0
    user = users[idx]

    print(f"\nFiring digest for user_id={user['user_id']} → telegram_id={user['telegram_id']}")
    print(f"Interests: {user['interests']}\n")

    # Build a minimal Bot instance just for sending
    from telegram import Bot
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)

    from src.scheduler.news_scheduler import NewsScheduler
    scheduler = NewsScheduler(bot=bot)

    async with bot:
        await scheduler._send_digest_to_user(
            user_id=user["user_id"],
            telegram_id=user["telegram_id"],
            interests=user["interests"],
        )

    print("\nDone — check your Telegram.")


if __name__ == "__main__":
    asyncio.run(main())
