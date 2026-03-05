"""
Google Calendar client using a service account.

Service Account Setup:
    1. Google Cloud Console → Create project → Enable Google Calendar API
    2. IAM & Admin → Service Accounts → Create service account
    3. Download JSON key file
    4. Share your Google Calendar with the service account email address
    5. Set GOOGLE_SERVICE_ACCOUNT_JSON env var (full JSON string or file path)
    6. Set GOOGLE_CALENDAR_ID (your calendar ID, usually your Gmail address)
    7. Set GOOGLE_CALENDAR_TIMEZONE (IANA timezone, e.g. "Asia/Singapore")
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config.settings import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]


class GoogleCalendarClient:
    """
    Wraps the Google Calendar API (v3) using a service account.

    The service is lazily created on first use and cached for the lifetime
    of the process. All times are stored/retrieved in RFC 3339 format.
    """

    def __init__(self):
        self._service = None

    def _get_service(self):
        """Lazily create and cache the Calendar API service."""
        if self._service is not None:
            return self._service

        creds_json = settings.GOOGLE_SERVICE_ACCOUNT_JSON
        if not creds_json:
            raise ValueError(
                "GOOGLE_SERVICE_ACCOUNT_JSON is not set. "
                "Set it to the full JSON string from your service account key file."
            )

        # Accept both a JSON string and a file path
        creds_json = creds_json.strip()
        if creds_json.startswith("{"):
            creds_info = json.loads(creds_json)
        else:
            with open(creds_json) as f:
                creds_info = json.load(f)

        credentials = service_account.Credentials.from_service_account_info(
            creds_info, scopes=SCOPES
        )
        self._service = build("calendar", "v3", credentials=credentials, cache_discovery=False)
        logger.info("Google Calendar service initialized.")
        return self._service

    @staticmethod
    def _to_rfc3339(dt: datetime) -> str:
        """Convert datetime to RFC 3339 string. Adds UTC offset if naive."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()

    @staticmethod
    def _parse_event(item: dict) -> dict:
        """Normalize a raw Google Calendar API event into a simplified dict."""
        start = item.get("start", {})
        end = item.get("end", {})
        return {
            "id": item.get("id", ""),
            "title": item.get("summary", "(no title)"),
            "start": start.get("dateTime") or start.get("date", ""),
            "end": end.get("dateTime") or end.get("date", ""),
            "location": item.get("location", ""),
            "description": item.get("description", ""),
            "all_day": "date" in start and "dateTime" not in start,
        }

    def get_events(self, start_dt: datetime, end_dt: datetime) -> list[dict]:
        """
        List calendar events between start_dt and end_dt.

        Returns a list of simplified event dicts with keys:
            id, title, start, end, location, description, all_day
        """
        try:
            service = self._get_service()
            result = (
                service.events()
                .list(
                    calendarId=settings.GOOGLE_CALENDAR_ID,
                    timeMin=self._to_rfc3339(start_dt),
                    timeMax=self._to_rfc3339(end_dt),
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            events = [self._parse_event(item) for item in result.get("items", [])]
            logger.info(f"Fetched {len(events)} events from {start_dt.date()} to {end_dt.date()}")
            return events
        except HttpError as e:
            logger.error(f"Google Calendar API error in get_events: {e}")
            raise

    def check_conflicts(self, start_dt: datetime, end_dt: datetime) -> list[dict]:
        """
        Return any existing events that overlap with the proposed time range.

        Args:
            start_dt: Proposed event start time.
            end_dt:   Proposed event end time.

        Returns:
            List of conflicting event dicts (empty if no conflicts).
        """
        return self.get_events(start_dt, end_dt)

    def create_event(
        self,
        title: str,
        start_dt: datetime,
        end_dt: datetime,
        description: str = "",
        location: str = "",
    ) -> dict:
        """
        Create a new calendar event.

        Returns a simplified dict with id, title, start, end, link.
        """
        try:
            service = self._get_service()
            tz = settings.GOOGLE_CALENDAR_TIMEZONE
            event_body = {
                "summary": title,
                "description": description,
                "location": location,
                "start": {"dateTime": self._to_rfc3339(start_dt), "timeZone": tz},
                "end": {"dateTime": self._to_rfc3339(end_dt), "timeZone": tz},
            }
            created = service.events().insert(
                calendarId=settings.GOOGLE_CALENDAR_ID,
                body=event_body,
            ).execute()

            result = {
                "id": created.get("id", ""),
                "title": created.get("summary", title),
                "start": created.get("start", {}).get("dateTime", ""),
                "end": created.get("end", {}).get("dateTime", ""),
                "link": created.get("htmlLink", ""),
            }
            logger.info(f"Created event '{title}' (id={result['id']})")
            return result
        except HttpError as e:
            logger.error(f"Google Calendar API error in create_event: {e}")
            raise

    def delete_event(self, event_id: str) -> bool:
        """
        Delete a calendar event by its Google Calendar event ID.

        Returns True on success.
        Raises HttpError if the event is not found or deletion fails.
        """
        try:
            service = self._get_service()
            service.events().delete(
                calendarId=settings.GOOGLE_CALENDAR_ID,
                eventId=event_id,
            ).execute()
            logger.info(f"Deleted event id={event_id}")
            return True
        except HttpError as e:
            logger.error(f"Google Calendar API error in delete_event: {e}")
            raise

    def get_time_insights(
        self, start_dt: datetime, end_dt: datetime
    ) -> dict:
        """
        Compute time management statistics for the given period.

        Returns a dict with:
            total_events, total_meeting_hours, avg_hours_per_day,
            busiest_day (name + hours), days_with_events, period_days
        """
        events = self.get_events(start_dt, end_dt)
        total_hours = 0.0
        by_day: dict[str, float] = {}

        for ev in events:
            if ev["all_day"]:
                continue
            try:
                start = datetime.fromisoformat(ev["start"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(ev["end"].replace("Z", "+00:00"))
                duration_h = (end - start).total_seconds() / 3600
                total_hours += duration_h
                day_key = start.strftime("%A %Y-%m-%d")
                by_day[day_key] = by_day.get(day_key, 0) + duration_h
            except Exception as e:
                logger.debug(f"Could not parse event times for insights: {e}")

        period_days = max((end_dt - start_dt).days, 1)
        busy_days = sorted(by_day.items(), key=lambda x: x[1], reverse=True)

        return {
            "total_events": len(events),
            "total_meeting_hours": round(total_hours, 1),
            "avg_hours_per_day": round(total_hours / period_days, 1),
            "busiest_day": busy_days[0] if busy_days else None,
            "days_with_events": len(by_day),
            "period_days": period_days,
        }


# Module-level singleton
gcal_client = GoogleCalendarClient()
