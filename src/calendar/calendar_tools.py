"""
Calendar tools: schemas and executor for Google Calendar operations.

These tools give Claude (Donna) the ability to read and write the user's calendar:
  - get_upcoming_events  — list upcoming events
  - check_conflicts      — find overlapping events for a proposed time slot
  - create_event         — add a new event (after user confirmation)
  - delete_event         — remove an event (after user confirmation)
  - get_time_insights    — compute time management statistics

Usage:
    executor = CalendarToolExecutor(gcal_client)
    result = executor.execute("get_upcoming_events", {"days": 7})
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool schemas (passed to Claude alongside the system prompt)
# ---------------------------------------------------------------------------

CALENDAR_TOOLS = [
    {
        "name": "get_upcoming_events",
        "description": (
            "Fetch the user's upcoming calendar events for the next N days. "
            "Use this when the user asks about their schedule, upcoming meetings, "
            "or what they have today/this week."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to look ahead (1 = today only, 7 = one week). Default: 7.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "check_conflicts",
        "description": (
            "Check whether any existing calendar events overlap with a proposed time slot. "
            "Always call this before creating a new event."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_datetime": {
                    "type": "string",
                    "description": (
                        "Proposed start time in ISO 8601 format: YYYY-MM-DDTHH:MM:SS. "
                        "Example: '2024-03-15T14:00:00'"
                    ),
                },
                "end_datetime": {
                    "type": "string",
                    "description": (
                        "Proposed end time in ISO 8601 format: YYYY-MM-DDTHH:MM:SS. "
                        "Example: '2024-03-15T15:30:00'"
                    ),
                },
            },
            "required": ["start_datetime", "end_datetime"],
        },
    },
    {
        "name": "create_event",
        "description": (
            "Create a new calendar event. Only call this after the user has explicitly confirmed "
            "the event details. Always check for conflicts first with check_conflicts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Event title/name.",
                },
                "start_datetime": {
                    "type": "string",
                    "description": "Event start time in ISO 8601 format: YYYY-MM-DDTHH:MM:SS.",
                },
                "end_datetime": {
                    "type": "string",
                    "description": "Event end time in ISO 8601 format: YYYY-MM-DDTHH:MM:SS.",
                },
                "description": {
                    "type": "string",
                    "description": "Optional event description or notes.",
                },
                "location": {
                    "type": "string",
                    "description": "Optional event location.",
                },
            },
            "required": ["title", "start_datetime", "end_datetime"],
        },
    },
    {
        "name": "delete_event",
        "description": (
            "Delete a calendar event by its Google Calendar event ID. "
            "Only call this after the user has explicitly confirmed the deletion."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "The Google Calendar event ID (from a previous get_upcoming_events call).",
                }
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "get_time_insights",
        "description": (
            "Compute time management statistics for the user's calendar over a given period. "
            "Use this when the user asks how their week went, how much time they spend in meetings, "
            "or for a schedule analysis. Default: past 7 days."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days_back": {
                    "type": "integer",
                    "description": "How many days back to analyze (default: 7, max: 30).",
                }
            },
            "required": [],
        },
    },
]


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


class CalendarToolExecutor:
    """
    Executes calendar tool calls from Claude against the Google Calendar API.

    Mirrors the structure of AgentToolExecutor in agent_tools.py.
    """

    def __init__(self, gcal_client):
        self.gcal = gcal_client

    def execute(self, tool_name: str, tool_input: dict) -> str:
        """
        Execute a named calendar tool with the given input dict.
        Returns a plain-text result string for Claude to use as tool_result.
        """
        try:
            if tool_name == "get_upcoming_events":
                return self._get_upcoming_events(tool_input.get("days", 7))
            elif tool_name == "check_conflicts":
                return self._check_conflicts(
                    tool_input.get("start_datetime", ""),
                    tool_input.get("end_datetime", ""),
                )
            elif tool_name == "create_event":
                return self._create_event(
                    tool_input.get("title", ""),
                    tool_input.get("start_datetime", ""),
                    tool_input.get("end_datetime", ""),
                    tool_input.get("description", ""),
                    tool_input.get("location", ""),
                )
            elif tool_name == "delete_event":
                return self._delete_event(tool_input.get("event_id", ""))
            elif tool_name == "get_time_insights":
                return self._get_time_insights(tool_input.get("days_back", 7))
            else:
                logger.warning(f"Unknown calendar tool called: {tool_name}")
                return f"Error: unknown tool '{tool_name}'."
        except Exception as e:
            logger.error(f"Calendar tool '{tool_name}' failed: {e}", exc_info=True)
            return f"Error executing '{tool_name}': {str(e)}"

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _parse_iso(dt_str: str) -> datetime:
        """Parse an ISO 8601 datetime string to a timezone-aware datetime (UTC)."""
        dt_str = dt_str.strip()
        # Handle 'Z' suffix
        dt_str = dt_str.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(dt_str)
        except ValueError:
            # Try without time (date-only)
            dt = datetime.strptime(dt_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    @staticmethod
    def _format_event(ev: dict) -> str:
        """Format a single event dict as a human-readable line."""
        title = ev["title"]
        start = ev["start"]
        end = ev["end"]
        loc = ev.get("location", "")

        # Parse dates for prettier display
        try:
            if ev.get("all_day"):
                start_fmt = datetime.fromisoformat(start).strftime("%A %b %d (all day)")
                end_fmt = ""
            else:
                start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
                start_fmt = start_dt.strftime("%a %b %d, %I:%M %p")
                end_fmt = end_dt.strftime("– %I:%M %p")
        except Exception:
            start_fmt = start
            end_fmt = ""

        line = f"📅 {title} — {start_fmt} {end_fmt}".strip()
        if loc:
            line += f" @ {loc}"
        line += f"  [id: {ev['id']}]"
        return line

    def _get_upcoming_events(self, days: int) -> str:
        days = max(1, min(int(days), 30))
        now = datetime.now(tz=timezone.utc)
        end = now + timedelta(days=days)
        events = self.gcal.get_events(now, end)

        if not events:
            period = "today" if days == 1 else f"the next {days} days"
            return f"No events found for {period}."

        lines = [f"Events for the next {days} day(s) ({len(events)} total):"]
        for ev in events:
            lines.append(self._format_event(ev))
        return "\n".join(lines)

    def _check_conflicts(self, start_str: str, end_str: str) -> str:
        if not start_str or not end_str:
            return "Error: start_datetime and end_datetime are required."

        start_dt = self._parse_iso(start_str)
        end_dt = self._parse_iso(end_str)

        if end_dt <= start_dt:
            return "Error: end_datetime must be after start_datetime."

        conflicts = self.gcal.check_conflicts(start_dt, end_dt)
        if not conflicts:
            return "No conflicts found. The time slot is free."

        lines = [f"⚠️ {len(conflicts)} conflict(s) found:"]
        for ev in conflicts:
            lines.append(self._format_event(ev))
        return "\n".join(lines)

    def _create_event(
        self,
        title: str,
        start_str: str,
        end_str: str,
        description: str = "",
        location: str = "",
    ) -> str:
        if not title.strip():
            return "Error: event title cannot be empty."
        if not start_str or not end_str:
            return "Error: start_datetime and end_datetime are required."

        start_dt = self._parse_iso(start_str)
        end_dt = self._parse_iso(end_str)

        if end_dt <= start_dt:
            return "Error: end_datetime must be after start_datetime."

        created = self.gcal.create_event(
            title=title.strip(),
            start_dt=start_dt,
            end_dt=end_dt,
            description=description,
            location=location,
        )

        link_part = f"\nCalendar link: {created['link']}" if created.get("link") else ""
        return (
            f"✅ Event created successfully.\n"
            f"Title: {created['title']}\n"
            f"Start: {created['start']}\n"
            f"End:   {created['end']}\n"
            f"ID:    {created['id']}"
            f"{link_part}"
        )

    def _delete_event(self, event_id: str) -> str:
        if not event_id.strip():
            return "Error: event_id cannot be empty."

        self.gcal.delete_event(event_id.strip())
        return f"✅ Event (id={event_id}) deleted successfully."

    def _get_time_insights(self, days_back: int) -> str:
        days_back = max(1, min(int(days_back), 30))
        now = datetime.now(tz=timezone.utc)
        start = now - timedelta(days=days_back)

        insights = self.gcal.get_time_insights(start, now)

        busiest = insights["busiest_day"]
        busiest_str = f"{busiest[0]} ({busiest[1]:.1f}h)" if busiest else "N/A"

        return (
            f"Time insights for the past {days_back} day(s):\n"
            f"  Total events:        {insights['total_events']}\n"
            f"  Total meeting hours: {insights['total_meeting_hours']}h\n"
            f"  Avg per day:         {insights['avg_hours_per_day']}h\n"
            f"  Busiest day:         {busiest_str}\n"
            f"  Days with events:    {insights['days_with_events']} of {insights['period_days']}"
        )
