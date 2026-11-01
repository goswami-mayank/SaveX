"""Supabase persistence and a durable, service-role-only notification worker."""

import logging
import os
from datetime import datetime, timezone

from supabase import create_client
from twilio.base.exceptions import TwilioRestException
from twilio.http.http_client import TwilioHttpClient
from twilio.rest import Client as TwilioClient

log = logging.getLogger("savex")
LOCATIONS = {"fridge", "freezer", "pantry", "other"}


def get_db(access_token=None):
    client = create_client(
        os.environ["SUPABASE_URL"], os.environ["SUPABASE_PUBLISHABLE_KEY"]
    )
    if access_token:
        client.postgrest.auth(access_token)
    return client


def get_admin_db():
    key = os.getenv("SUPABASE_SECRET_KEY")
    return create_client(os.environ["SUPABASE_URL"], key) if key else None


def sms_enabled():
    return os.getenv("ENABLE_EXTERNAL_NOTIFICATIONS", "false").lower() == "true"


def whatsapp_enabled():
    return (
        sms_enabled()
        and os.getenv("ENABLE_WHATSAPP_NOTIFICATIONS", "false").lower() == "true"
    )


def deliver_job(db, job):
    """Return status + text. Ambiguous SMS results are never retried automatically."""
    items = (
        db.table("items")
        .select("name,status,expiry_date")
        .eq("id", job["item_id"])
        .execute()
        .data
    )
    if (
        not items
        or items[0]["status"] != "active"
        or items[0]["expiry_date"] != job["expiry_snapshot"]
    ):
        return "skipped", "Item is no longer eligible."
    item = items[0]
    remaining = (
        datetime.fromisoformat(item["expiry_date"]).date()
        - datetime.fromisoformat(job["local_day"]).date()
    ).days
    message = (
        f"SaveX: {item['name']} expires today."
        if remaining == 0
        else f"SaveX: {item['name']} expires in {remaining} day(s)."
    )
    if job["channel"] == "app":
        return "sent", message
    if job["channel"] == "call_mock":
        return (
            "sent",
            f"Mock call: {item['name']} expires today. No actual call was placed.",
        )
    if job["channel"] not in {"sms", "whatsapp"}:
        return "failed", "Unsupported notification channel."
    users = (
        db.table("users")
        .select("whatsapp_number")
        .eq("id", job["user_id"])
        .execute()
        .data
    )
    number = users[0].get("whatsapp_number") if users else None
    if not number:
        return "skipped", "No recipient number configured."
    sender = (
        os.getenv("TWILIO_WHATSAPP_FROM")
        if job["channel"] == "whatsapp"
        else os.getenv("FROM_PHONE")
    )
    if (
        not sender
        or not os.getenv("TWILIO_ACCOUNT_SID")
        or not os.getenv("TWILIO_AUTH_TOKEN")
    ):
        return "failed", "Messaging sender credentials are not configured."
    destination = (
        "whatsapp:" + number.removeprefix("whatsapp:")
        if job["channel"] == "whatsapp"
        else number
    )
    try:
        TwilioClient(
            os.environ["TWILIO_ACCOUNT_SID"],
            os.environ["TWILIO_AUTH_TOKEN"],
            http_client=TwilioHttpClient(timeout=10),
        ).messages.create(to=destination, from_=sender, body=message)
        return (
            "sent",
            message,
        )  # Twilio accepted the message; handset delivery is not confirmed.
    except TwilioRestException as exc:
        log.warning("Message request failed with status %s", exc.status)
        return (
            "failed" if exc.status and 400 <= exc.status < 500 else "unknown"
        ), "Message delivery failed or could not be confirmed."
    except Exception:
        log.warning("Message outcome uncertain; do not retry automatically")
        return "unknown", "Message delivery could not be confirmed."


def run_alerts(db, today=None, *, user_id=None, now=None, max_jobs=200):
    """Enqueue today's jobs and atomically claim due work; never change the system clock."""
    if today is not None:
        raise ValueError("Use the read-only expiry preview for date simulation")
    timestamp = now or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ValueError("Scheduler timestamp must include a timezone")
    stamp = timestamp.isoformat()
    created = (
        db.rpc(
            "enqueue_notification_jobs",
            {
                "p_now": stamp,
                "p_timezone": os.getenv("NOTIFICATION_TIMEZONE", "Asia/Kolkata"),
                "p_user_id": user_id,
            },
        )
        .execute()
        .data
    )
    processed = 0
    outcomes = {"sent": 0, "failed": 0, "unknown": 0, "skipped": 0}
    for _ in range(max_jobs):
        jobs = (
            db.rpc(
                "claim_notification_job_v2",
                {
                    "p_now": stamp,
                    "p_sms_enabled": sms_enabled(),
                    "p_user_id": user_id,
                    "p_whatsapp_enabled": whatsapp_enabled(),
                },
            )
            .execute()
            .data
        )
        if not jobs:
            break
        job = jobs[0]
        try:
            status, message = deliver_job(db, job)
        except Exception:
            # App and mock call work can be retried after the lease expires; an SMS
            # exception before delivery is conservatively marked uncertain.
            log.exception("Notification job %s failed before completion", job["id"])
            status, message = (
                ("unknown", "Message delivery could not be confirmed.")
                if job["channel"] in {"sms", "whatsapp"}
                else ("failed", "Notification could not be processed.")
            )
        finished = (
            db.rpc(
                "finish_notification_job",
                {"p_job_id": job["id"], "p_status": status, "p_message": message},
            )
            .execute()
            .data
        )
        if finished:
            processed += 1
            outcomes[status] += 1
    return {
        "enqueued": created,
        "processed": processed,
        "outcomes": outcomes,
        "sms_enabled": sms_enabled(),
    }
