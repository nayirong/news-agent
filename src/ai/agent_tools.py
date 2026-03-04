"""
Agent management tools: schemas and executor for database/scheduler operations.

These tools give Claude the ability to actually modify the user's environment:
  - Interests (add, remove, set, get)
  - Delivery schedule (update_delivery_time)

Usage:
    executor = AgentToolExecutor(user_id, telegram_id, db_manager, scheduler)
    result = executor.execute("add_interest", {"interest": "Machine Learning"})
    executor.reschedule_if_needed(user_dict)
"""
import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool schemas (passed to Claude alongside web_search)
# ---------------------------------------------------------------------------

MANAGEMENT_TOOLS = [
    {
        "name": "get_interests",
        "description": "Get the user's current list of news interests from the database.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "add_interest",
        "description": (
            "Add a single new topic to the user's interest list without removing existing ones. "
            "Use this when the user wants to add one topic."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "interest": {
                    "type": "string",
                    "description": "The topic to add, e.g. 'Machine Learning', 'NBA', 'Climate Tech'",
                }
            },
            "required": ["interest"],
        },
    },
    {
        "name": "remove_interest",
        "description": (
            "Remove a single topic from the user's interest list. "
            "Use this when the user wants to stop receiving news about a specific topic."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "interest": {
                    "type": "string",
                    "description": "The topic to remove, e.g. 'NBA'",
                }
            },
            "required": ["interest"],
        },
    },
    {
        "name": "set_interests",
        "description": (
            "Replace the user's entire interest list with a new set of topics. "
            "Use this when the user wants to start fresh or significantly change their interests."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "interests": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Complete new list of topics, e.g. ['AI', 'Climate Tech', 'NBA']",
                }
            },
            "required": ["interests"],
        },
    },
    {
        "name": "update_delivery_time",
        "description": (
            "Change the user's daily digest delivery time. "
            "Use this when the user asks to change what time they receive their news digest."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "time": {
                    "type": "string",
                    "description": "Delivery time in HH:MM format (24-hour UTC), e.g. '08:30' or '20:00'",
                }
            },
            "required": ["time"],
        },
    },
]


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

class AgentToolExecutor:
    """
    Executes management tool calls from Claude against the actual database and scheduler.

    Tracks whether interests were changed so the caller can reschedule the user
    after the conversation ends.
    """

    def __init__(self, user_id: int, telegram_id: int, db_manager, scheduler=None):
        self.user_id = user_id
        self.telegram_id = telegram_id
        self.db_manager = db_manager
        self.scheduler = scheduler
        self.interests_changed = False

    def execute(self, tool_name: str, tool_input: dict) -> str:
        """
        Execute a named tool with the given input dict.
        Returns a plain-text result string for Claude to use as tool_result.
        """
        try:
            if tool_name == "get_interests":
                return self._get_interests()
            elif tool_name == "add_interest":
                return self._add_interest(tool_input.get("interest", ""))
            elif tool_name == "remove_interest":
                return self._remove_interest(tool_input.get("interest", ""))
            elif tool_name == "set_interests":
                return self._set_interests(tool_input.get("interests", []))
            elif tool_name == "update_delivery_time":
                return self._update_delivery_time(tool_input.get("time", ""))
            else:
                logger.warning(f"Unknown management tool called: {tool_name}")
                return f"Error: unknown tool '{tool_name}'."
        except Exception as e:
            logger.error(f"Tool '{tool_name}' execution failed: {e}", exc_info=True)
            return f"Error executing '{tool_name}': {str(e)}"

    def reschedule_if_needed(self, user: dict) -> None:
        """
        If interests were modified via tools, reschedule the user's digest job.
        Call this after answer_question() returns.
        """
        if not self.interests_changed or not self.scheduler:
            return
        interests = self.db_manager.get_interests(self.user_id)
        if interests:
            self.scheduler.reschedule_user(
                user_id=self.user_id,
                telegram_id=self.telegram_id,
                interests=interests,
                delivery_time=user["delivery_time"],
                digest_chat_id=user.get("digest_chat_id"),
            )
            logger.info(
                f"Rescheduled digest for user_id={self.user_id} "
                f"after interest change via agent tools"
            )

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _get_interests(self) -> str:
        interests = self.db_manager.get_interests(self.user_id)
        if not interests:
            return "No interests set yet."
        return f"Current interests ({len(interests)}): {', '.join(interests)}"

    def _add_interest(self, interest: str) -> str:
        interest = interest.strip()
        if not interest:
            return "Error: interest name cannot be empty."

        # Normalize to title-case for consistency
        normalized = interest.title()

        # Check if it already exists (case-insensitive)
        existing = self.db_manager.get_interests(self.user_id)
        existing_lower = [i.lower() for i in existing]
        if normalized.lower() in existing_lower:
            return f"'{normalized}' is already in your interests: {', '.join(existing)}"

        self.db_manager.add_interest(self.user_id, normalized)
        self.interests_changed = True
        updated = self.db_manager.get_interests(self.user_id)
        return f"Added '{normalized}'. Your interests are now: {', '.join(updated)}"

    def _remove_interest(self, interest: str) -> str:
        interest = interest.strip()
        if not interest:
            return "Error: interest name cannot be empty."

        # Find the actual stored name (case-insensitive match)
        existing = self.db_manager.get_interests(self.user_id)
        match = next((i for i in existing if i.lower() == interest.lower()), None)

        if not match:
            return (
                f"'{interest}' was not found in your interests. "
                f"Current interests: {', '.join(existing) if existing else 'none'}"
            )

        self.db_manager.remove_interest(self.user_id, match)
        self.interests_changed = True
        updated = self.db_manager.get_interests(self.user_id)
        remaining = ', '.join(updated) if updated else 'none'
        return f"Removed '{match}'. Remaining interests: {remaining}"

    def _set_interests(self, interests: list) -> str:
        cleaned = [i.strip().title() for i in interests if i.strip()]
        if not cleaned:
            return "Error: cannot set an empty interest list."

        self.db_manager.set_interests(self.user_id, cleaned)
        self.interests_changed = True
        return f"Interests updated to: {', '.join(cleaned)}"

    def _update_delivery_time(self, time_str: str) -> str:
        time_str = time_str.strip()
        if not re.match(r'^([01]?\d|2[0-3]):[0-5]\d$', time_str):
            return (
                f"Error: '{time_str}' is not a valid time. "
                "Use HH:MM format (24-hour UTC), e.g. '08:30' or '20:00'."
            )

        self.db_manager.update_delivery_time(self.user_id, time_str)

        # Reschedule immediately since we have the new time
        if self.scheduler:
            interests = self.db_manager.get_interests(self.user_id)
            if interests:
                self.scheduler.reschedule_user(
                    user_id=self.user_id,
                    telegram_id=self.telegram_id,
                    interests=interests,
                    delivery_time=time_str,
                )
                logger.info(
                    f"Rescheduled digest for user_id={self.user_id} "
                    f"to {time_str} UTC via agent tool"
                )

        return f"Delivery time updated to {time_str} UTC."
