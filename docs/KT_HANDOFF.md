# SaveX — coding-agent knowledge transfer

Date: 2026-11-01. Workspace: `/workspaces/codespaces-blank/SaveX`.

## Read this first

The user explicitly stopped feature implementation and requested **basic setup plus this handoff**. The product is NOT complete. Do not describe the scaffold, backend audio routes, or migration as an end-to-end verified POC. The initial four-minute target was not achieved. A subsequent agent, identified by the user as Astra, will review code quality and continue only as instructed.

Read the complete five-page `SaveX_Architecture.pdf` and this document before modifying behavior. There is no AGENTS.md in the inspected repository/parent tree. Existing source and templates were untracked at the beginning; no commits were created, and no existing source was intentionally deleted. `.env` is ignored, has not been edited, and must remain private.

## Approved decisions and latest scope

- Next.js mobile-first PWA; Python/FastAPI; Supabase PostgreSQL.
- Exact models: `gpt-live-transcribe` for live STT; `gpt-live-1` for browser conversation; `gpt-5.4-mini-2026-03-17` for extraction/planning.
- Official OpenAI SDK required. No alternative models/providers were substituted.
- User approved retaining **existing Supabase email/password Auth + RLS**, with migration from `profiles` to the PDF's `users(name, whatsapp_number)` model.
- User approved **GPT-Live client delegation + mandatory on-screen grocery confirmation**. Live must not mutate inventory.
- User explicitly deferred **all Twilio calling**. Browser AI audio remains in the intended POC scope. “gpt realtime AI audio” was interpreted in context as the approved browser Live conversation, not approval to silently substitute a different model ID.
- Twilio WhatsApp and in-app expiry notifications remain required. SMS was an existing-repository deviation, not a newly approved product channel.
- No real messages or calls have been sent. External delivery must remain disabled unless explicitly authorized and configured.
- Retain APScheduler with a single backend process. Supabase's existing client is retained instead of adding SQLModel and a second connection approach. No Redis, queues, microservices, hosting platform, offline sync, or component library added.
- Cerebras `qwen-3.8-27b` remains a FUTURE, benchmark-gated migration. No Cerebras request adapter was implemented or used.

## Baseline assessment

| Area | PDF | Initial repository | Requested target/current status |
|---|---|---|---|
| UI | React Native/Expo | Jinja templates | Next.js scaffold now builds; functional screens missing |
| Voice input | recorded m4a → Whisper | local faster-whisper webm upload | Realtime transcription relay written; browser capture missing |
| Reasoning | Mistral | Mistral Codestral HTTP calls | Official OpenAI Responses structured parsing adapter written |
| Voice output | absent | absent | Live WebRTC signaling/delegation routes written; browser media missing |
| Identity | seeded user, users table | Supabase Auth + profiles | Auth retained; users migration written, NOT applied |
| Database access | SQLModel/Postgres | Supabase client + RLS | Existing client retained; SQLModel not introduced |
| Notifications | WhatsApp + app | SMS + app | WhatsApp adapter written; no actual deliveries tested |
| Scheduler | daily around 08:00 | background scheduler | daily 08:00 UTC, explicitly disabled by default |
| Confirmation | required | old web cards | API supports confirmed records; new UI not implemented |
| Missing details | confirmation | defaulted date/shelf life | nullable drafts; confirmed saves require complete fields |
| Planner | 3 meals, priority within 3d | fabricated priority fallback; weak validation | deterministic ingredient validation, no fake priorities, one invalid-result retry |
| Demo date | simulate date | not implemented | read-only expiry preview endpoint; UI missing |
| Calls | absent | absent | deferred by user |

The PDF's local faster-whisper fallback is removed because the user specified exact OpenAI live STT. Do not reintroduce provider fallback silently.

## Repository map

- `main.py`: FastAPI application, retained legacy auth/template pages, inventory routes and aliases, health/readiness, expiry preview, audio-router registration. Root `.env` is loaded here.
- `services.py`: Supabase clients, alert classification orchestration, grouped WhatsApp sending, database unique-key alert claims.
- `backend/domain.py`: Pydantic schemas; required confirmed fields; expiry calculation; threshold ladder; priority selection; meal rule validation; read-only date preview.
- `backend/llm.py`: `StructuredProvider` protocol and `OpenAIProvider`; exact fixed model; extraction and meal orchestration. `LLM_PROVIDER` rejects unsupported providers instead of silently falling back.
- `backend/audio.py`: authenticated STT WebSocket relay; Live session SDP signaling through official SDK; backend client-delegation request handler. These are partial/unverified integration code, not a completed audio feature.
- `schema.sql`: transactional fresh-install schema + compatibility migration. Preserves old profiles/SMS history. Requires Supabase SQL Editor or an actual database connection.
- `frontend/`: Next.js app-router project; package lock; TypeScript config; buildable static setup page; responsive plain CSS; manifest/icon; service-worker file. No UI library.
- `templates/`: original auth/profile/dashboard pages, retained as references. **Old dashboard voice uploads are incompatible with the new JSON `/api/voice` endpoint.** Do not present it as the finished UI.
- `tests/test_foundation.py`: mocked/unit foundation checks. `pytest.ini` configures repository import path.
- `.env.example`: safe configuration template. `.gitignore` excludes credentials, caches, and build artifacts.
- `requirements.txt`: human-maintained dependency ranges. `requirements.lock.txt`: installed Python dependency snapshot. `frontend/package-lock.json`: npm lock.

## Setup and actual evidence

Use README.md for commands. Python dependencies are installed in `.venv`; npm dependencies in `frontend/node_modules`. Workspace Python is 3.14; Node is 24.20.0. Current resolved OpenAI SDK is 2.54.0 and Next.js is 16.4.3.

Executed checks:

- Python code was formatted with Ruff. Basic syntax/undefined-name/import checks (`E4,E7,E9,F`, excluding module-placement E402) were run. The broader inherited Ruff rules still flag broad exception catches, FastAPI `Depends` argument defaults, and nested context managers; this is not a full clean lint result.
- `.venv/bin/python -m pytest -q`: **24 passed**. One dependency warning: Starlette's TestClient deprecated its httpx integration. This is not a test failure; resolve deliberately rather than adding unrelated runtime packages.
- `npm --prefix frontend run build`: **passed**, including TypeScript validation and static page generation.
- OpenAI `models.retrieve` returned success for each of the three exact requested model IDs. This verifies metadata access, NOT generation quality, Realtime handshakes, Live WebRTC, browser audio, or quota under load. No generated AI output was tested against the remote API.
- Supabase REST connection is reachable. Admin-key `select(...).limit(0)` requests returned **PGRST205** for `profiles`, `users`, `items`, and `alerts_log`: the required tables were missing in the configured project.
- No database persistence, migration execution, browser microphone, PWA installation, RLS isolation across actual accounts, WhatsApp delivery, or real Live session was verified.

Foundation tests cover threshold boundaries/overdue classification, leap dates, multi-item mocked extraction, incomplete drafts, invalid saves, update schema restrictions, meal schema/ingredient/priority rules, one retry, missing priority reporting, upstream failure propagation, preview without mutation, health/unauthenticated inventory, sanitized database failure, and unauthenticated WebSocket rejection.

Still missing: authenticated item-update/state-transition API tests; real/concurrent alert-dedup tests; authenticated midstream Realtime failure tests; frontend and end-to-end tests. The mocks do not demonstrate actual model extraction accuracy.

## Database blocker — be precise

The user's `.env` was inspected twice, using variable names only. It contains:

`CEREBRAS_API_KEY`, `EXA_API_KEY`, `OPENAI_API_KEY`, `OPENAI_MODEL_NAME`, `VOICE_MODEL_NAME`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `FROM_PHONE`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`, `SUPABASE_JWKS_URL`.

At the last check, neither file nor process environment contained `DATABASE_URL`, `SUPABASE_DB_URL`, `POSTGRES_URL`, `POSTGRES_PRISMA_URL`, or `SUPABASE_ACCESS_TOKEN`. The user said the envs were set; distinguish **existing REST credentials** from the SQL connection/management credential needed to apply DDL. Do not expose credentials, claim they are missing altogether, derive passwords, or attempt undocumented SQL execution through REST.

Next step is running `schema.sql` in Supabase SQL Editor, or applying it through a newly supplied PostgreSQL connection. The migration has NOT been applied. Existing code now references `users`, so user-specific access requires that migration.

Schema notes for review:

- `users` references `auth.users`; existing `profiles` rows copy over when present. Original profiles table is preserved.
- Core item fields remain unchanged. New items reference the domain users table as well as the existing auth identity relationship. Compatibility FK is `NOT VALID`; review/backfill any existing orphan records and explicitly validate it before production use.
- `alerts_log.user_id` and `message` already existed; retained for RLS, grouping, and inbox text. `delivery_status` is the only newly added alert column, disclosed before implementation.
- Unique `(item_id, level, channel)` supports independent app/WhatsApp claims. Legacy `sms` is retained only for historical rows.
- Delivery status is `pending/sent/failed/unknown`. `sent` currently means provider acceptance, NOT handset delivery. `sent_at` is inserted at claim time; improve timestamp semantics before treating it as confirmed delivery time.
- RLS checks identity and item ownership. Test cross-user reads, mutations, and alert claims with two actual users before declaring isolation verified.
- Add/review SQL-level constraints for expiry consistency and existing-table validation; current migration's `CREATE TABLE IF NOT EXISTS` does not retrofit every new-table constraint on a pre-existing items table.

## API inventory

Canonical routes and `/api` aliases exist for the PDF REST endpoints:

- `POST /voice` and `/api/voice`: **JSON** `{transcript: string}` → `{transcript, items: DraftItem[]}`. Does not accept recorded files. Drafts can contain nulls and clarification text.
- `POST /items`: `{items: [{name,bought_date,shelf_days,location}]}` → `{saved: number}`. Date and shelf life are required; expiry is computed server-side. Quantity text is extraction review metadata, NOT an added database column.
- `GET /items`: non-used inventory ordered by expiry, including expired display states; returns days_left and level.
- `PATCH /items/{id}`: allowlisted editable fields and active/used status; recalculates expiry. Empty patches, explicit nulls, unknown fields, invalid states are rejected.
- `GET /alerts`: recent app + WhatsApp history, including delivery status. UI must distinguish inbox from delivery history.
- `POST /plan`: three validated meals plus priority list and a clear notice if no items expire within three days. Expired ingredients are excluded.
- `POST /api/alerts/read`, `POST /api/alerts/check`: mark app alerts read / execute checks within caller RLS.
- `POST /api/expiry/preview`: `{as_of:"YYYY-MM-DD"}` → classifications only; no clock change, persisted mutations, or delivery.
- `GET /api/health`: process health only.
- `GET /api/ready`: checks users table and delivery_status reachability; returns 503 until migration. This is a minimal readiness check, not full schema/integration validation.
- `WS /api/voice/stream`: auth cookie + exact `APP_ORIGIN` required. Client sends `{type:"audio",audio:base64PCM16}` at 24kHz mono, then `{type:"commit"}`. Server sends ready, provider deltas/completion/errors. One committed turn per connection; two-minute limit.
- `POST /api/live/session`: `{sdp}` → documented OpenAI Live WebRTC session response. Disabled unless `LIVE_ENABLED=true`.
- `POST /api/live/delegate`: `{transcript}` → classified read-only pantry/plan task or grocery proposals. Returns commentary for the browser to send with the original delegation ID. Never saves items.

FastAPI `/docs` provides generated schemas. Response models are not consistently typed yet; finish typed responses/error contracts before claiming the API requirement is complete.

## Audio architecture and official references

1. STT uses Realtime `wss://api.openai.com/v1/realtime?intent=transcription`, with `session.update` type transcription, PCM16/24000, and the exact STT model. `gpt-live-transcribe` requires explicit commits and does not support server/semantic VAD. Browser capture, audio worklet/resampling, item-ID-based transcript reconciliation, microphone cleanup and error UI still need implementation. Test Next.js WebSocket upgrade proxy behavior; do not assume HTTP rewrites prove upgrade support.
2. Live uses WebRTC with `POST /v1/live/sessions`, client delegation, and `gpt-live-1`. Browser must request microphone, add audio tracks, establish the data channel before SDP offer, wait for ICE gathering, apply `result.transport.sdp`, then wait for `session.started`. Do not send `session.start` on WebRTC.
3. Installed Python SDK 2.54.0 has no typed `client.live`. Current code uses its generic `client.post` for the documented Live endpoint. Verify the returned shape and error handling with a real session. Do not invent a TTS method or silently replace the model.
4. Client delegation needs input/output transcript history. `session.delegation.created` contains metadata/ID, NOT task text. Browser must forward context to FastAPI, render returned grocery drafts for review, and send `session.commentary.append` with the exact delegation ID. Support interruption, stale results and graceful `session.close`/`session.closed` cleanup. No browser implementation currently exists.
5. FastAPI remains responsible for business rules and all data mutations. Model-suggested actions must not bypass screen confirmation.

Official sources reviewed:

- https://developers.openai.com/api/docs/guides/realtime-transcription
- https://developers.openai.com/api/docs/guides/live
- https://developers.openai.com/api/docs/guides/live-delegation
- https://developers.openai.com/api/docs/guides/voice-webrtc
- https://developers.openai.com/api/docs/guides/voice-websockets
- https://developers.openai.com/api/docs/models/gpt-5.4-mini

Twilio sandbox/template rules from the PDF still require verification against current official Twilio documentation before enabling real sending. No template fallback was implemented. Do not invent approved template IDs or assume `FROM_PHONE` is a WhatsApp sender; `TWILIO_WHATSAPP_FROM` needs explicit configuration.

## Reliability review priorities

- A single FastAPI worker with APScheduler is the POC scheduling model. Do not run multiple independent schedulers. Backend downtime means scheduled work is unavailable; no high-availability guarantee exists.
- Current alert classification chooses the most urgent applicable threshold (7..4 slight, 3..2 moderate, 1..0 high), skips already-claimed same-level/channel records, and expires negative-day items without sending expired WhatsApp messages. It does not backfill every crossed threshold. Test against the PDF and stakeholder expectations.
- Unique database claims prevent duplicate concurrent claims, but external Twilio sends and database writes are not one atomic transaction. Pending/unknown rows are not retried automatically; reconcile provider logs before retrying. A crash can therefore miss a delivery. Do not claim exactly-once delivery or robust retries.
- Add tests for actual Supabase/PostgREST `upsert(ignore_duplicates=True)` return behavior, group membership, partial failures and concurrent claims before relying on notification semantics.
- Add database/network timeout handling beyond PostgREST APIError. Current generic AI error paths are sanitized but broad; avoid hiding programmer errors in production.
- Cookie origin checks are present; `COOKIE_SECURE` defaults false for localhost. Set true for HTTPS; check actual proxy origins, auth refresh behavior and CSRF coverage before exposure.
- Review concurrent item edits and update-not-found races. Current item editing reads then updates without optimistic concurrency.
- Review JWT/session lifetime over a long audio connection and memory/concurrency limits. No rate limiter or high-availability infrastructure was added.
- Frontend `sw.js` is a lifecycle-only file and is NOT registered yet. Manifest currently has SVG only; add appropriate raster install icons and real-device install verification. Do not claim installability from manifest existence alone.
- `.env` values for `OPENAI_MODEL_NAME` and `VOICE_MODEL_NAME` are deliberately not used to override exact approved model IDs. Document any future configurability explicitly.

## Recommended continuation order

1. Review this partial code, resolve foundational issues above, and apply/verify migration. Confirm readiness, signup/login/profile flow and two-user RLS.
2. Build real Pantry, Voice input/review, Alerts and Planner screens with plain React state and typed API helpers. Avoid extra frameworks. Required confirmed fields must remain blank until supplied; display quantity_text and clarification without inventing stored quantities.
3. Integrate STT browser capture/live transcript; confirm and persist multiple items end to end. Add actual failure/reconnection tests without duplicating saved records.
4. Verify alert claim behavior and scheduled checks; implement grouping, unread inbox and preview UI. Keep external delivery off while mocking Twilio. Verify sandbox/template restrictions before authorized sending.
5. Integrate real Live WebRTC conversation/client delegation and secure cleanup. Verify grocery proposals, pantry questions and meal results by voice; no autonomous writes.
6. Add missing critical tests and smoke-test mobile browser microphone/install flows. Demonstrate a full flow before claiming POC readiness. Keep calls deferred.

## Future Cerebras migration / evaluation

`StructuredProvider.generate(system,payload,schema)` is the current minimal seam. Add a Cerebras adapter only after verifying official SDK/API, exact `qwen-3.8-27b` availability and structured-output capabilities. Business functions remain provider-independent; both adapters must return validated Pydantic values. Do not assume OpenAI-specific `.responses.parse` exists elsewhere.

No benchmark harness or dataset exists yet. Prepare a versioned JSONL set with explicit expected groceries, missing/ambiguous fields, dates, several items, adversarial transcripts, and pantry/priority meal cases. Run the same inputs and semantic validators for both providers. Record model/provider/configuration, input case ID, extraction accuracy, schema validity, meal compliance, total latency, TTFT only when supported by the implemented transport, throughput at specified concurrency, usage/cost using verified published rates, errors and retries. Establish acceptance thresholds with the user before changing defaults. No performance equivalence or migration approval has been established.
