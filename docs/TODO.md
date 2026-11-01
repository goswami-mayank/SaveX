# Todo and verification status

## Blocking end-to-end readiness

- [x] Apply `schema.sql` to the configured Supabase project; `/api/ready` returns 200. The migration ran through the project’s IPv4 session pooler using the database password from `.env`.
- [x] Verify food and household persistence, alert-log uniqueness, and two-user RLS in a real PostgreSQL transaction; all test records were rolled back.
- [x] Verify sign-in and food/household persistence and updates through the app using a temporary confirmed test account; the account and data were deleted.
- [ ] Verify self-service signup and email confirmation with a real user email and the deployed origin configured in Supabase Auth.
- [x] Verify browser microphone streaming and GPT-Live connection using a simulated microphone and a temporary authenticated user.
- [x] Verify a synthetic Hindi spoken request through GPT-Live, including a review card and missing-date handling.
- [ ] Verify natural speech, playback, interruptions, and connection failures on a physical device.
- [x] Verify responsive navigation at 320 px and 390 px and service-worker registration in headless Chromium.
- [ ] Verify PWA installation and layout on a physical mobile device.
- [x] Obtain explicit authorization, enable scheduled Twilio SMS in the current workspace, and run one controlled live test. Twilio reported the test delivered; the result is in alert history.
- [ ] Keep WhatsApp separately disabled unless authorized and configured with an enrolled recipient and correct 24-hour/template behavior. Calls remain mocked.

## Backend hardening

- [x] Verify scheduled-job uniqueness, atomic RPC claims, and sequential alert deduplication with the live database.
- [x] Verify concurrent alert claims with real database integration tests. The SMS-enabled worker was also tested with a mocked Twilio client: four SMS attempts, four in-app alerts, and one mocked call without duplicates. Delivery `sent` means accepted by Twilio, not delivered. Pending/unknown sends require reconciliation; no exactly-once guarantee exists.
- [ ] Add live delivery callbacks or an approved template workflow if needed for production; outside the service window the free-form message currently sent by this POC can fail.
- [ ] Validate the compatibility foreign key after backfilling existing users, and audit legacy tables/constraints before deploying an existing production database.
- [ ] Improve concurrent item updates, end-to-end structured response contracts, database failure observability, and session lifecycle under unstable connections.
- [ ] Independently evaluate generated meal instructions: validation checks the declared ingredient list and priority coverage, but cannot prove free-text steps omit every unlisted ingredient.
- [x] Verify the Cerebras API key using synthetic extraction and three-meal planning; switch the configured workspace to Cerebras.
- [ ] Compare Cerebras extraction quality, meal compliance, latency, and cost against OpenAI on a representative dataset.

## Completed checks

- [x] Verify the exact 10-minute, 1-hour, 4-hour, and 12-hour offsets, 10:00 weekly slot, mocked call, queue reactivation, RLS, and no duplicate claims.

- [x] Ten focused test scenarios pass (provider calls mocked in the suite).
- [x] OpenAI exact-model extraction produced two complete records; Realtime transcription session configuration was accepted.
- [x] Exa returned recipe sources; the OpenAI planner returned three validated meals with priority ingredients using those sources.
- [x] Related Exa photos appear inside meal cards with source links; live searches found photos for three dishes and the mobile fallback was checked with a blocked image.
- [x] Local Next.js and FastAPI started; proxied health and readiness returned 200 after migration, and unauthenticated WebSocket upgrade reached the backend and was refused.
- [x] Production frontend build and TypeScript checks passed.
- [x] A real headless WebRTC handshake received `session.started` and `session.closed` from GPT-Live; browser microphone and playback still need human testing.
