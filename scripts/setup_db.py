"""
Initialize the SQLite database and create all tables.

Run once before starting the bot for the first time, or any time
you need to reset/re-create the database schema.

Usage:
    python scripts/setup_db.py

From the project root directory.
"""
import sys
import os

# Add project root to path so imports resolve correctly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.db_manager import db_manager

if __name__ == "__main__":
    db_manager.init_db()
    print("Database initialized successfully.")
    print(f"Database location: {db_manager.engine.url}")
