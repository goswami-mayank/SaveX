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

OpenAI handles realtime audio. For extraction and meal planning, `LLM_PROVIDER` selects OpenAI (default) or Cerebras; set `CEREBRAS_API_KEY` and `CEREBRAS_MODEL=qwen-3.8-27b` before selecting `cerebras`. Restart FastAPI after editing `.env`. The Cerebras adapter uses strict structured output and validates responses again in the backend. Verify the key and model with `.venv/bin/python -m scripts.check_cerebras` before switching; this makes real Cerebras requests but does not write inventory or send notifications. Compare extraction and meal quality before relying on the new provider. No automatic provider fallback is used.

`EXA_API_KEY` enables optional recipe research and related, source-linked photos in meal cards. This uses up to three additional concurrent Exa searches per researched plan. `LIVE_ENABLED` defaults to true for user-initiated browser sessions. `SCHEDULER_ENABLED` defaults to true for the minute-by-minute queue worker; run **one** FastAPI worker or disable it on other workers. `NOTIFICATION_TIMEZONE` defaults to Asia/Kolkata. `ENABLE_EXTERNAL_NOTIFICATIONS` defaults to false. Real SMS delivery defaults to disabled in new environments. It has been explicitly authorized and enabled in the current workspace; one live test was reported delivered by Twilio. The expiry-day call is mocked. The original WhatsApp channel remains separately opt-in and requires an approved sender and applicable template or customer-service window. Calling is deferred.




