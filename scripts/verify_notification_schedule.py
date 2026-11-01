"""Read-only integration check of the deployed notification cadence; sends nothing."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from supabase import create_client

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
zone_name = "Asia/Kolkata"
zone = ZoneInfo(zone_name)
admin = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"])
day = date(2026, 11, 1)
midnight = datetime(2026, 11, 1, tzinfo=zone)


def check(start, days, expected):
    result = (
        admin.rpc(
            "preview_notification_schedule",
            {
                "p_start": start.isoformat(),
                "p_local_day": day.isoformat(),
                "p_expiry": (day + timedelta(days=days)).isoformat(),
                "p_timezone": zone_name,
            },
        )
        .execute()
        .data
    )
    actual = sorted(
        datetime.fromisoformat(row["scheduled_at"]).astimezone(timezone.utc)
        for row in result
    )
    assert actual == sorted(x.astimezone(timezone.utc) for x in expected), (
        f"Unexpected cadence for {days} days remaining"
    )


check(midnight, 7, [midnight + timedelta(hours=10)])
check(midnight, 3, [midnight + timedelta(minutes=n) for n in (10, 60, 240)])
check(midnight, 0, [midnight + timedelta(minutes=n) for n in (10, 60, 240, 720)])
start = midnight + timedelta(hours=9)
check(start, 3, [start + timedelta(minutes=n) for n in (10, 60, 240)])
late = midnight + timedelta(hours=18)
check(late, 0, [late + timedelta(minutes=n) for n in (10, 60, 240)])
print("Notification cadence verified; no records changed and no messages sent.")
