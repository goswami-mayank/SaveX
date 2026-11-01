# SaveX

SaveX is a Progressive Web App (PWA) for tracking food expiry dates, locating household items, receiving reminders, and discovering meals based on what is already in your pantry.

The application uses **FastAPI** for authentication, validation, persistence, provider integrations, and notifications, with **Next.js** powering the user interface.

## Project status

The interface and backend are implemented. The configured Supabase project has the required schema, and database persistence, alert deduplication, and cross-user isolation have passed rollback-only checks.

The following still require human verification:

- Browser voice functionality
- SMS Notification
- Complete end-to-end user flows

For more details, see the [project documentation](docs/PROJECT.md), [todo and status](docs/TODO.md), and [changelog](CHANGELOG.md).

## Requirements

- Python 3.11 or later
- Node.js 20.9 or later
- A Supabase project
- The configured provider accounts required by the features you intend to use

## Setup

### 1. Install dependencies

From the project root, create a virtual environment and install the Python and frontend dependencies:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.lock.txt
npm --prefix frontend ci
```

### 2. Configure environment variables

For a fresh setup, copy `.env.example` to `.env` and fill in the required credentials.

```bash
cp .env.example .env
```

The current workspace already has a `.env` file. **Never commit or disclose this file or its credentials.**

### 3. Set up the database

For a new Supabase project, apply `schema.sql` through the Supabase SQL Editor or a PostgreSQL connection. The migration has already been applied to the Supabase project currently configured for this workspace.

> Supabase REST credentials cannot be used to apply SQL migrations.

### 4. Start the application

Run the backend and frontend in separate terminals from the project root.

**Terminal 1 — FastAPI backend**

```bash
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
```

**Terminal 2 — Next.js frontend**

```bash
npm --prefix frontend run dev
```

Open the application at [http://localhost:3000](http://localhost:3000). FastAPI's interactive API documentation is available at [http://localhost:8000/docs](http://localhost:8000/docs).

## Deployment and URLs

- Localhost and this workspace's forwarded Codespaces URL are accepted automatically.
- For other deployments, set `APP_ORIGIN` to the exact browser origin and configure `BACKEND_URL` for the Next.js server.
- Microphone access requires HTTPS or localhost.
- Supabase Authentication's allowed redirect URLs must include `<APP_ORIGIN>/login`.
- The Next.js server proxies API requests and the legacy authentication/profile pages.

After applying the database migration, log in or create an account.

Users who do not have a phone number can still receive in-app alerts. WhatsApp notifications require a configured sender and recipient.

## Tests and validation

Run the focused test suite and build the frontend:

```bash
.venv/bin/python -m pytest -q
npm --prefix frontend run build
```

An optional read-only check of the deployed notification queue schedule is also available. It does not send notifications:

```bash
.venv/bin/python scripts/verify_notification_schedule.py
```

## Configuration

### AI and recipe research

- Approved OpenAI model IDs are fixed in the backend.
- `EXA_API_KEY` enables optional recipe research and related, source-linked photos in meal cards.
- Recipe research can perform up to three additional concurrent Exa searches per researched meal plan.

### Live sessions and scheduler

- `LIVE_ENABLED` defaults to `true` for user-initiated browser sessions.
- `SCHEDULER_ENABLED` defaults to `true` for the minute-by-minute notification queue worker.
- Run only **one** FastAPI worker with the scheduler enabled, or disable the scheduler on additional workers.
- `NOTIFICATION_TIMEZONE` defaults to `Asia/Kolkata`.

### External notifications

- `ENABLE_EXTERNAL_NOTIFICATIONS` defaults to `false`.
- Real SMS delivery defaults to disabled in new environments. It has been explicitly authorized and enabled in the current workspace; one live test was reported as delivered by Twilio.
- The expiry-day call is mocked.
- The original WhatsApp channel remains separately opt-in and requires an approved sender and an applicable template or customer-service window.
- Calling is deferred.

### Health and readiness endpoints

- `GET /api/health` reports process liveness.
- `GET /api/ready` checks required Supabase tables using `SUPABASE_SECRET_KEY`. It returns HTTP `503` if the required schema or database connectivity is missing.

A successful readiness response does **not** prove that row-level security (RLS), model calls, or messaging work end to end.

## Reminder schedule

All reminder times use the `Asia/Kolkata` timezone by default.

| Food expiry window | Reminder schedule |
| --- | --- |
| 4–7 days remaining | One reminder at 10:00 |
| 1–3 days remaining | Three daily reminders: 10 minutes, 1 hour, and 4 hours after the day's schedule start |
| Expiring today | The three reminders above, plus a 12-hour offset and one simulated call at the first reminder |

### How reminder timing works

- On the first day, reminder offsets are measured from the time the item is saved.
- On subsequent days, offsets are measured from local midnight.
- Offsets that fall after midnight are not sent for the previous day. As a result, an item saved late in the day may receive fewer than the maximum number of reminders that day.
- A notification job that is more than 30 minutes late is skipped to avoid a burst of reminders after downtime.

### Example

For an item saved at **09:00** with **1–3 days remaining**, reminders are scheduled for **09:10**, **10:00**, and **13:00** on that day. On later eligible days, the offsets restart from local midnight: **00:10**, **01:00**, and **04:00**.

## Notification demonstration

In the **Alerts** section, select **Developer notification demo** to run an accelerated, read-only simulation using the same database schedule.

The demonstration:

- Does not send SMS messages.
- Does not place calls.
- Does not change the system clock.
- Does not modify saved items.

To receive real SMS messages, add your phone number in **Account settings**. Real SMS is enabled in the current workspace. WhatsApp remains a separate opt-in channel and requires the appropriate sender and messaging configuration.





















