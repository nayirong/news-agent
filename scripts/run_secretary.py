"""
Entry point for running the Aria Calendar Secretary bot standalone.

Prerequisites:
    1. Copy .env.example to .env and fill in:
       - TELEGRAM_BOT_TOKEN_SECRETARY (from @BotFather — a second bot)
       - ANTHROPIC_API_KEY
       - GOOGLE_SERVICE_ACCOUNT_JSON (full JSON string from your service account key)
       - GOOGLE_CALENDAR_ID (your Gmail address or calendar ID)
       - GOOGLE_CALENDAR_TIMEZONE (e.g. "Asia/Singapore")
    2. Run: python scripts/setup_db.py  (if not already done)
    3. Verify that 0. Agents/Calendar Agent/*.md files exist

Usage:
    python scripts/run_secretary.py

Run from the project root directory.
"""
import sys
import os
import logging

# Resolve the project root (parent of this script's directory)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ensure imports resolve correctly regardless of where the script is called from
sys.path.insert(0, PROJECT_ROOT)

# Change to project root so relative paths (agent files, SQLite DB, logs) work
os.chdir(PROJECT_ROOT)

# Configure logging before importing other modules
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from src.bot.secretary_bot import main

if __name__ == "__main__":
    main()
