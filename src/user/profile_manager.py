"""
ProfileManager: High-level user profile operations.

Acts as a facade over db_manager for the bot layer.
Provides interest parsing, onboarding state detection, and feedback handling.

Usage:
    from src.user.profile_manager import profile_manager

    user = profile_manager.get_or_create_user(telegram_id=12345)
    interests = profile_manager.set_interests_from_text(user["user_id"], "AI, NBA, climate tech")
    if profile_manager.looks_like_interest_list("AI, NBA, climate tech"):
        ...
"""
import logging
import re
from typing import Optional

from src.database.db_manager import db_manager

logger = logging.getLogger(__name__)

# Weight deltas for feedback reactions
FEEDBACK_POSITIVE_DELTA = 0.3
FEEDBACK_NEGATIVE_DELTA = -0.3


class ProfileManager:
    """
    Manages user profiles and interest preferences.
    Used by telegram_bot.py to interact with user data.
    """

    def get_or_create_user(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
    ) -> dict:
        """Get an existing user or create a new one. Returns a user dict."""
        return db_manager.get_or_create_user(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
        )

    def get_user(self, telegram_id: int) -> Optional[dict]:
        """Look up a user by Telegram ID. Returns None if not found."""
        return db_manager.get_user_by_telegram_id(telegram_id)

    def set_interests_from_text(self, user_id: int, text: str) -> list[str]:
        """
        Parse a comma-separated interest string and save to the database.

        Normalizes: strips whitespace, title-cases each interest,
        filters out empty tokens.

        Example:
            "AI, climate tech, NBA" → ["Ai", "Climate Tech", "Nba"]

        Returns the parsed list of interests saved.
        """
        raw_parts = [part.strip() for part in text.split(",")]
        interests = [part.title() for part in raw_parts if len(part.strip()) > 1]

        if interests:
            db_manager.set_interests(user_id, interests)
            logger.info(f"Set interests for user_id={user_id}: {interests}")

        return interests

    def add_interest(self, user_id: int, interest: str) -> None:
        """Add a single interest to the user's list without removing others."""
        db_manager.add_interest(user_id, interest)

    def remove_interest(self, user_id: int, interest: str) -> None:
        """Remove a single interest from the user's list by exact name."""
        db_manager.remove_interest(user_id, interest)

    def get_interests(self, user_id: int) -> list[str]:
        """Return the user's interests, ordered by weight descending."""
        return db_manager.get_interests(user_id)

    def has_interests(self, user_id: int) -> bool:
        """Return True if the user has at least one interest set."""
        return len(self.get_interests(user_id)) > 0

    def update_delivery_time(self, user_id: int, delivery_time: str) -> bool:
        """
        Update the user's preferred daily delivery time.

        Validates HH:MM format before saving.

        Returns:
            True if updated successfully, False if the format is invalid.
        """
        if not re.match(r"^\d{2}:\d{2}$", delivery_time):
            return False
        db_manager.update_delivery_time(user_id, delivery_time)
        return True

    def record_positive_feedback(self, user_id: int, interest: str) -> None:
        """Increase the weight of an interest based on a 👍 reaction."""
        db_manager.update_interest_weight(user_id, interest, FEEDBACK_POSITIVE_DELTA)

    def record_negative_feedback(self, user_id: int, interest: str) -> None:
        """Decrease the weight of an interest based on a 👎 reaction."""
        db_manager.update_interest_weight(user_id, interest, FEEDBACK_NEGATIVE_DELTA)

    @staticmethod
    def looks_like_interest_list(text: str) -> bool:
        """
        Heuristic to detect whether a message is a list of interests
        (vs. a question to Claude).

        Criteria for treating as an interest list:
        - Contains at least one comma (multiple topics)
        - Under 200 characters (not a detailed message)
        - Does not end with a question mark
        - Does not start with common question-word patterns

        This heuristic is intentionally conservative — when in doubt,
        treat the message as a question (which is the safer fallback).
        """
        text = text.strip()

        if not text or "," not in text or len(text) >= 200:
            return False

        if text.endswith("?"):
            return False

        question_starters = (
            "what", "who", "when", "where", "why", "how",
            "tell me", "explain", "describe", "is ", "are ",
            "can ", "do ", "did ", "has ", "have ", "will ",
            "could ", "would ", "should ",
        )
        lower = text.lower()
        if any(lower.startswith(qs) for qs in question_starters):
            return False

        return True


# Module-level singleton
profile_manager = ProfileManager()
