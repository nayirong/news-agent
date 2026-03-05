"""
Quick sanity check for the Google Calendar connection.

Run this before starting the bot to verify:
  1. GOOGLE_SERVICE_ACCOUNT_JSON is valid and parseable
  2. The service account can authenticate with Google
  3. It has read access to your calendar (GOOGLE_CALENDAR_ID)

Usage:
    python scripts/test_calendar.py
"""
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

from datetime import datetime, timedelta, timezone
from config.settings import settings
from src.calendar.gcal_client import gcal_client

print("=== Google Calendar Connection Test ===\n")

# 1. Check env vars
print(f"GOOGLE_CALENDAR_ID:       {settings.GOOGLE_CALENDAR_ID or '❌ NOT SET'}")
print(f"GOOGLE_CALENDAR_TIMEZONE: {settings.GOOGLE_CALENDAR_TIMEZONE or '❌ NOT SET'}")
json_preview = settings.GOOGLE_SERVICE_ACCOUNT_JSON[:60] + "..." if settings.GOOGLE_SERVICE_ACCOUNT_JSON else "❌ NOT SET"
print(f"GOOGLE_SERVICE_ACCOUNT_JSON: {json_preview}\n")

if not settings.GOOGLE_SERVICE_ACCOUNT_JSON:
    print("❌ GOOGLE_SERVICE_ACCOUNT_JSON is not set. Add it to your .env file.")
    sys.exit(1)

# 2. Try to connect and fetch events
print("Connecting to Google Calendar API...")
try:
    now = datetime.now(tz=timezone.utc)
    events = gcal_client.get_events(now, now + timedelta(days=7))
    print(f"✅ Connected! Found {len(events)} event(s) in the next 7 days.\n")

    if events:
        print("Upcoming events:")
        for ev in events:
            print(f"  • {ev['title']} — {ev['start']}")
    else:
        print("(Calendar is clear for the next 7 days.)")

    # 3. Test insights
    print("\nTesting time insights (past 7 days)...")
    insights = gcal_client.get_time_insights(now - timedelta(days=7), now)
    print(f"✅ Insights: {insights['total_events']} events, {insights['total_meeting_hours']}h in meetings\n")

    print("=== All checks passed! You're ready to run the bot. ===")
    print("Run: python scripts/run_secretary.py")

except Exception as e:
    print(f"❌ Connection failed: {e}")
    print("\nCommon fixes:")
    print("  • Check that GOOGLE_SERVICE_ACCOUNT_JSON contains the full JSON (not a file path)")
    print("  • Verify the Calendar API is enabled in your Google Cloud project")
    print("  • Confirm you shared your calendar with the service account email")
    print(f"    (look for 'client_email' in your JSON key)")
    sys.exit(1)
