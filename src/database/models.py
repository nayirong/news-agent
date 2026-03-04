"""
SQLAlchemy ORM models.

Intentionally minimal: we store user preferences, not articles.
Claude searches the web in real-time, so there is nothing to cache.

Tables:
    users            — Telegram user with delivery preferences
    user_interests   — Topics the user wants news about (with weights for feedback)
    conversations    — Recent message/response pairs for follow-up Q&A context
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()


class User(Base):
    """
    Telegram user with delivery preferences.
    One user can have many interests and many conversation records.
    """
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)
    timezone = Column(String, default="UTC")
    delivery_time = Column(String, default="08:00")
    # Where to send scheduled digests. None = private DM (telegram_id).
    # Set to a group chat_id via /digesthere to receive digests in a group.
    digest_chat_id = Column(Integer, nullable=True)

    interests = relationship(
        "UserInterest",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    conversations = relationship(
        "Conversation",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(telegram_id={self.telegram_id}, username={self.username!r})>"


class UserInterest(Base):
    """
    A single topic of interest for a user.

    weight: 1.0 = normal, higher = more important, lower = less important.
    Weight is adjusted by feedback: 👍 increases (+0.3), 👎 decreases (-0.3).
    Clamped to range [0.1, 5.0].
    """
    __tablename__ = "user_interests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False, index=True)
    interest = Column(String, nullable=False)
    weight = Column(Float, default=1.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="interests")

    def __repr__(self) -> str:
        return f"<UserInterest(interest={self.interest!r}, weight={self.weight})>"


class Conversation(Base):
    """
    Recent conversation history for follow-up Q&A context.

    Stores the last N exchanges per user. Older records are pruned
    by get_recent_conversations(limit=N). Not used for long-term memory.
    """
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False, index=True)
    message = Column(Text, nullable=False)
    response = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="conversations")

    def __repr__(self) -> str:
        return f"<Conversation(user_id={self.user_id}, created_at={self.created_at})>"
