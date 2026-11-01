# SaveX

A mobile-first PWA for food expiry, household item locations, alerts, and pantry-aware meals. FastAPI controls authentication, validation, persistence, provider calls, and notifications; Next.js provides the interface.

**Current status:** The interface and backend are implemented. The configured Supabase project has the schema; database persistence, alert deduplication, and cross-user isolation passed rollback-only checks. Browser voice, mobile installation, WhatsApp delivery, and complete end-to-end flows require human verification. See [project documentation](docs/PROJECT.md), [todo/status](docs/TODO.md), and [changelog](CHANGELOG.md).

## Setup

Requirements: Python 3.11+, Node.js 20.9+, Supabase project, and the configured provider accounts.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.lock.txt
npm --prefix frontend ci
```

Copy `.env.example` to `.env` for a fresh setup and enter credentials. The workspace already has `.env`; never commit or disclose it. For a new Supabase project, apply `schema.sql` using Supabase SQL Editor or a PostgreSQL connection. The migration was applied to the currently configured project. REST credentials do not apply SQL migrations.

In separate terminals run:

```bash
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
npm --prefix frontend run dev
```

Open http://localhost:3000. FastAPI docs: http://localhost:8000/docs. Localhost and this workspace’s forwarded Codespaces URL are accepted automatically. Set `APP_ORIGIN` to the exact browser origin and `BACKEND_URL` for Next.js for other deployments. Microphone access requires HTTPS or localhost. Supabase authentication's allowed redirect URLs must include `<APP_ORIGIN>/login`.

The Next server proxies API and legacy auth/profile pages. Log in or create an account after the migration has been applied. Users without a phone number can still use in-app alerts; WhatsApp requires a configured sender and recipient.

Run the focused suite and frontend build:

```bash
.venv/bin/python -m pytest -q
npm --prefix frontend run build
# Optional read-only check of the deployed queue schedule; sends nothing:
.venv/bin/python scripts/verify_notification_schedule.py
```

## Configuration

OpenAI handles realtime audio. For extraction and meal planning, `LLM_PROVIDER` selects OpenAI (default) or Cerebras; set `CEREBRAS_API_KEY` and `CEREBRAS_MODEL=qwen-3.8-27b` before selecting `cerebras`. Restart FastAPI after editing `.env`. The Cerebras adapter uses strict structured output and validates responses again in the backend. Verify the key and model with `.venv/bin/python -m scripts.check_cerebras` before switching; this makes real Cerebras requests but does not write inventory or send notifications. Compare extraction and meal quality before relying on the new provider. No automatic provider fallback is used.

`EXA_API_KEY` enables optional recipe research and related, source-linked photos in meal cards. This uses up to three additional concurrent Exa searches per researched plan. `LIVE_ENABLED` defaults to true for user-initiated browser sessions. `SCHEDULER_ENABLED` defaults to true for the minute-by-minute queue worker; run **one** FastAPI worker or disable it on other workers. `NOTIFICATION_TIMEZONE` defaults to Asia/Kolkata. `ENABLE_EXTERNAL_NOTIFICATIONS` defaults to false. Real SMS delivery defaults to disabled in new environments. It has been explicitly authorized and enabled in the current workspace; one live test was reported delivered by Twilio. The expiry-day call is mocked. The original WhatsApp channel remains separately opt-in and requires an approved sender and applicable template or customer-service window. Calling is deferred.

`GET /api/health` is process liveness. `GET /api/ready` checks required Supabase tables using `SUPABASE_SECRET_KEY`; it returns 503 if required schema or connectivity is missing. It is not proof that RLS, model calls, or messaging work end to end.

## Reminder schedule and demonstration

In Asia/Kolkata, food with 4–7 days remaining has one reminder at 10:00. Food with 1–3 days remaining has three daily reminder offsets: 10 minutes, one hour, and four hours. Food expiring today has those three plus a 12-hour offset and one simulated call at the first reminder. Offsets are measured from item save time on its first day, then from local midnight on subsequent days. Offsets falling after midnight are not sent for the previous day, so an item saved late in the day can have fewer than the maximum number of reminders that day. A job more than 30 minutes late is skipped to avoid a burst after downtime.

In Alerts, **Developer notification demo** runs an accelerated, read-only simulation using the same database schedule. It never sends SMS, places a call, changes the system clock, or alters saved items. Set your phone number in Account settings to receive SMS; real SMS is enabled in the current workspace. For example, an item saved at 09:00 with 1–3 days remaining is scheduled for 09:10, 10:00, and 13:00 that day; on later eligible days the offsets restart at 00:10, 01:00, and 04:00.
