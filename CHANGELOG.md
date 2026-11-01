# Changelog

## Exa recipe photos

- Added source-linked related photos inside each meal card when Exa research is selected. Image searches run concurrently and missing or blocked photos do not prevent meal planning.
- Verified live Exa results for three meals and the mobile card layout, including failed-image fallback; the focused test suite still contains ten scenarios.

## Live SMS activation

- With explicit authorization, enabled scheduled Twilio SMS in the current workspace and sent one controlled live test through the notification worker. Twilio reported the test delivered. The test remains in alert history; its synthetic item was marked used.
- Kept expiry-day calls mocked and WhatsApp separately disabled. Automated tests explicitly disable the scheduler and outbound delivery regardless of environment settings.

## Hinglish voice and scheduled reminders

- Recognize Hindi-English mixed grocery requests, preserve explicit expiry dates separately from unknown purchase dates, and require review before saving. Improved live transcript handling and failure diagnostics.
- Added a PostgreSQL-backed notification queue, minute cron worker, Asia/Kolkata schedule, SMS adapter, in-app reminders, and an expiry-day mocked call. The original WhatsApp channel remains separately disabled by default.
- Added an accelerated notification demo that uses the real scheduling policy without sending messages or altering the clock. Verified a synthetic Hindi speech request in a browser, real database queue concurrency, and an expiry-day run with a mocked SMS provider; temporary test data was removed.

## Confirmation redirect and recovery

- Default confirmation redirects to the current Codespace URL when no explicit origin is configured. Added confirmation-link resend and clear expired-link messaging; authentication fragments are removed from browser history. Supabase Auth URL configuration must still allow the chosen origin.

## Signup error handling

- Reject passwords shorter than six characters before sign-up and show Supabase password errors on the form instead of returning HTTP 500. Authentication service outages now show a retry message. Added regression coverage.

## V1 test release

- Verified sign-in, multi-item extraction, food updates, household CRUD, in-app alert deduplication, and an Exa-backed meal plan against the configured Supabase project with a temporary account; the account and data were removed.
- Verified mobile browser sign-in and confirmation, Realtime microphone connection, GPT-Live connection, and responsive navigation at 320 px and 390 px. Audio used a simulated microphone.
- Fixed form label associations, the Next.js development indicator covering mobile navigation, and alert layout overflow on narrow screens.

## 2026-11-01 — Supabase migration applied

- Applied `schema.sql` to the configured Supabase project via the IPv4 session pooler. All four tables have RLS enabled and application readiness returns 200.
- Verified food and household inserts, alert deduplication, and cross-user isolation in a rolled-back transaction; no test records were retained.

## 2026-11-01 — Household, recipe research, and PWA

- Replaced the setup screen with a responsive steel/monotone interface using generated shadcn/ui controls. Added pantry, household inventory, review-before-save, alerts, and meal-plan views.
- Added household item storage for name, category, location, and recording time, independent of food expiry. Added typed create, batch create, list, update, delete, and extraction endpoints with Supabase RLS.
- Added Exa recipe research using the documented Search API, optional in meal planning and available through voice delegation. Exa snippets are untrusted and meal-plan ingredient/priority validation remains mandatory.
- Wired browser live transcription and GPT-Live WebRTC/client delegation to backend routes; household location requests and proposal review are supported. Browser and device verification remain outstanding.
- Added PWA install assets and service-worker registration. Offline synchronization is not included.
- Kept phone numbers optional during sign-up; corrected the email confirmation redirect to the configured frontend origin. Kept real WhatsApp sends disabled by default; enabled the single-worker daily in-app scheduler and added an explicit check and read-only date preview.
- Replaced the initial parameterized suite with ten focused scenario tests. Verified actual Exa search, OpenAI two-item extraction, live transcription session setup, and a three-meal plan with Exa research.
- Fixed inherited backend helper imports and the OpenAI SDK Live response type; verified a real WebRTC session starts and closes. Added Codespaces forwarded-origin support.
- Updated the transactional schema for household storage, compatibility backfill, expiry integrity, alert uniqueness and row-level security; checked it with a PostgreSQL parser.
- Added project documentation, changelog, and todo/status log. Supabase migration was subsequently applied, as recorded above.

## Foundation

- Created FastAPI, Supabase schema, structured food extraction and validated meal rules, notification adapter, Next.js scaffold, and agent handoff. See `docs/KT_HANDOFF.md` for the original assessment; its snapshot status predates this release.
