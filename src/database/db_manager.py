"""
DatabaseManager: all read/write operations against SQLite via SQLAlchemy.

Uses a context-manager session pattern. Each method opens a session,
performs its work, and closes it. No sessions are left open across calls.

Usage:
    from src.database.db_manager import db_manager

    user = db_manager.get_or_create_user(telegram_id=12345)
    db_manager.set_interests(user["user_id"], ["AI", "Climate Tech"])
    interests = db_manager.get_interests(user["user_id"])
"""
import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from config.settings import settings
from src.database.models import Base, User, UserInterest, Conversation

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self, database_url: Optional[str] = None):
        url = database_url or settings.DATABASE_URL
        self.engine = create_engine(url, echo=False)
        self._SessionFactory = sessionmaker(bind=self.engine)

    def init_db(self) -> None:
        """Create all tables if they do not already exist, then run migrations."""
        Base.metadata.create_all(self.engine)
        self._run_migrations()
        logger.info("Database tables created (or already exist)")

    def _run_migrations(self) -> None:
        """Apply schema migrations for columns added after initial release."""
        from sqlalchemy import text
        with self.engine.connect() as conn:
            # v2.2: digest_chat_id — where to deliver scheduled digests
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN digest_chat_id INTEGER"))
                conn.commit()
                logger.info("Migration: added digest_chat_id to users table")
            except Exception:
                pass  # column already exists

    @contextmanager
    def get_session(self):
        """Context manager: yields a session, commits on success, rolls back on error."""
        session = self._SessionFactory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # -------------------------------------------------------------------------
    # User operations
    # -------------------------------------------------------------------------

    def get_or_create_user(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
    ) -> dict:
        """
        Get a user by telegram_id, creating one if they don't exist.

        Returns a plain dict (not an ORM object) to avoid detached-instance issues
        after the session closes.
        """
        with self.get_session() as session:
            user = session.query(User).filter_by(telegram_id=telegram_id).first()

            if not user:
                user = User(
                    telegram_id=telegram_id,
                    username=username,
                    first_name=first_name,
                    delivery_time=settings.DEFAULT_DELIVERY_TIME,
                    timezone=settings.DEFAULT_TIMEZONE,
                )
                session.add(user)
                session.flush()
                logger.info(f"Created new user: telegram_id={telegram_id}")
            else:
                user.last_active = datetime.utcnow()
                if username:
                    user.username = username

            return {
                "user_id": user.user_id,
                "telegram_id": user.telegram_id,
                "username": user.username,
                "delivery_time": user.delivery_time,
                "timezone": user.timezone,
                "digest_chat_id": user.digest_chat_id,
            }

    def get_user_by_telegram_id(self, telegram_id: int) -> Optional[dict]:
        """Return user dict or None if not found."""
        with self.get_session() as session:
            user = session.query(User).filter_by(telegram_id=telegram_id).first()
            if not user:
                return None
            return {
                "user_id": user.user_id,
                "telegram_id": user.telegram_id,
                "username": user.username,
                "delivery_time": user.delivery_time,
                "timezone": user.timezone,
                "digest_chat_id": user.digest_chat_id,
            }

    def update_digest_chat(self, user_id: int, chat_id: Optional[int]) -> None:
        """Set where scheduled digests are delivered. None = private DM."""
        with self.get_session() as session:
            user = session.query(User).filter_by(user_id=user_id).first()
            if user:
                user.digest_chat_id = chat_id
                dest = f"chat_id={chat_id}" if chat_id else "private DM"
                logger.info(f"Updated digest destination for user_id={user_id} to {dest}")

    def update_delivery_time(self, user_id: int, delivery_time: str) -> None:
        """Update a user's preferred daily digest delivery time (HH:MM format)."""
        with self.get_session() as session:
            user = session.query(User).filter_by(user_id=user_id).first()
            if user:
                user.delivery_time = delivery_time
                logger.info(f"Updated delivery_time for user_id={user_id} to {delivery_time}")

    # -------------------------------------------------------------------------
    # Interest operations
    # -------------------------------------------------------------------------

    def set_interests(self, user_id: int, interests: list[str]) -> None:
        """
        Replace all interests for a user with the provided list.
        This is a full replacement — existing interests are deleted first.
        """
        with self.get_session() as session:
            session.query(UserInterest).filter_by(user_id=user_id).delete()
            for interest in interests:
                cleaned = interest.strip()
                if cleaned:
                    session.add(UserInterest(user_id=user_id, interest=cleaned))
            logger.info(f"Set {len(interests)} interests for user_id={user_id}")

    def add_interest(self, user_id: int, interest: str) -> None:
        """Add a single interest without removing existing ones."""
        with self.get_session() as session:
            existing = (
                session.query(UserInterest)
                .filter_by(user_id=user_id, interest=interest.strip())
                .first()
            )
            if not existing:
                session.add(UserInterest(user_id=user_id, interest=interest.strip()))
                logger.info(f"Added interest '{interest}' for user_id={user_id}")

    def remove_interest(self, user_id: int, interest: str) -> None:
        """Remove a single interest by exact name match."""
        with self.get_session() as session:
            session.query(UserInterest).filter_by(
                user_id=user_id, interest=interest.strip()
            ).delete()
            logger.info(f"Removed interest '{interest}' for user_id={user_id}")

    def get_interests(self, user_id: int) -> list[str]:
        """Return list of interest strings, ordered by weight descending."""
        with self.get_session() as session:
            interests = (
                session.query(UserInterest)
                .filter_by(user_id=user_id)
                .order_by(UserInterest.weight.desc())
                .all()
            )
            return [i.interest for i in interests]

    def update_interest_weight(self, user_id: int, interest: str, delta: float) -> None:
        """
        Adjust the weight of a specific interest by delta.
        Clamps result to [0.1, 5.0] to prevent runaway values.

        Typical deltas: +0.3 for 👍, -0.3 for 👎.
        """
        with self.get_session() as session:
            interest_row = (
                session.query(UserInterest)
                .filter_by(user_id=user_id, interest=interest)
                .first()
            )
            if interest_row:
                new_weight = max(0.1, min(5.0, interest_row.weight + delta))
                interest_row.weight = new_weight
                logger.info(
                    f"Updated weight for '{interest}' "
                    f"(user_id={user_id}): {new_weight:.2f}"
                )

    # -------------------------------------------------------------------------
    # Scheduler support
    # -------------------------------------------------------------------------

    def get_all_users_with_preferences(self) -> list[dict]:
        """
        Return all users who have at least one interest defined.
        Used by the scheduler on startup to load and schedule all digests.
        """
        with self.get_session() as session:
            users = session.query(User).all()
            result = []
            for user in users:
                interests = [i.interest for i in user.interests]
                if interests:
                    result.append({
                        "user_id": user.user_id,
                        "telegram_id": user.telegram_id,
                        "interests": interests,
                        "delivery_time": user.delivery_time,
                        "timezone": user.timezone,
                        "digest_chat_id": user.digest_chat_id,
                    })
            return result

    # -------------------------------------------------------------------------
    # Conversation history
    # -------------------------------------------------------------------------

    def save_conversation(self, user_id: int, message: str, response: str) -> None:
        """Save a user message and agent response for conversation context."""
        with self.get_session() as session:
            session.add(Conversation(
                user_id=user_id,
                message=message,
                response=response,
            ))

    def get_recent_conversations(self, user_id: int, limit: int = 5) -> list[dict]:
        """
        Return the last N conversations for a user, oldest first.
        Used to build context for follow-up Q&A calls.
        """
        with self.get_session() as session:
            convos = (
                session.query(Conversation)
                .filter_by(user_id=user_id)
                .order_by(Conversation.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {"message": c.message, "response": c.response}
                for c in reversed(convos)
            ]


# Module-level singleton
db_manager = DatabaseManager()
