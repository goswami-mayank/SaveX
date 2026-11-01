# SaveX project guide

## Product model

Food records contain name, purchase date, shelf life, calculated expiry date, storage location, and state. The backend calculates expiry and classifies 7/3/1-day thresholds; negative days move an active item to expired. Only confirmed food is saved. The pantry is sorted by expiry. The planner uses active food, prioritizes food expiring within three days, and permits salt, oil, water, and spices as additional basics. When no priority food exists, the response says so.

Household records are separate because many household objects have no purchase or expiry date. Each has a name, user-specified category, location, and recorded timestamp. Missing category or location is requested during review. The time defaults to the time of logging unless supplied explicitly. Explicit timestamps must include a time-zone offset. Household items do not generate expiry alerts or appear as recipe ingredients.

## Components and flows

- Next.js PWA: shadcn/ui-generated components, responsive desktop and mobile navigation, food and household listing/editing, voice note review, alerts, and meal planner.
- FastAPI: authenticated, RLS-scoped requests, schema validation, expiry arithmetic, AI coordination, scheduler, and Twilio delivery.
- Supabase: `users`, `items`, `household_items`, and `alerts_log`; migration in `schema.sql`. Retains Supabase Auth and row-level security.
- `gpt-live-transcribe`: browser PCM16 audio streams through a FastAPI WebSocket to an OpenAI Realtime transcription session. The user stops recording to commit a turn; the session returns incremental and final transcripts.
- `gpt-5.4-mini-2026-03-17` or Cerebras `qwen-3.8-27b`: configurable structured food/household extraction and meal planning. Cerebras uses its OpenAI-compatible chat endpoint with strict JSON Schema; backend Pydantic and pantry rules still validate the result, and invalid meal plans retry once. No save happens before user confirmation. This workspace uses Cerebras after a live synthetic extraction and planning check; OpenAI is the default for fresh environments.
- `gpt-live-1`: browser WebRTC audio; client delegation routes household location queries, grocery/household proposals, pantry questions, meal plans and requested recipe research to FastAPI. Session responses never mutate the database. User must confirm proposals on screen.
- Exa: optional bounded search of pantry ingredients via `POST https://api.exa.ai/search` using `EXA_API_KEY`; linked recipe sources and highlights inform planning. After a validated plan is generated, up to three concurrent searches find related photos, with the source linked inside each meal card. Photo search or loading failures leave the plan usable; research failures are surfaced. Snippets are untrusted data and cannot override ingredient/priority rules.
- APScheduler runs a cron-style worker each minute. Supabase persists notification jobs, claims them atomically, and records each delivery slot in `alerts_log`. SMS and in-app alerts follow the requested Asia/Kolkata cadence; the expiry-day call is simulated. Real SMS and WhatsApp are disabled by default in a new environment. SMS is enabled in the current workspace after explicit authorization; WhatsApp remains disabled.

## API

FastAPI `/docs` is the live API reference. Key routes:

| Route | Purpose |
| --- | --- |
| `POST /api/voice` | Extract multiple grocery drafts from a transcript. |
| `WS /api/voice/stream` | Stream 24 kHz mono PCM16 live transcription. |
| `POST /api/items`, `GET /api/items`, `PATCH /api/items/{id}` | Confirm, list, edit or mark food used. |
| `POST /api/household/extract` | Extract household item drafts from a transcript. |
| `GET /api/household`, `POST /api/household`, `POST /api/household/batch`, `PATCH /api/household/{id}`, `DELETE /api/household/{id}` | Manage user-owned household records. Batch insert avoids partially saved review lists. |
| `GET /api/alerts`, `POST /api/alerts/read`, `POST /api/alerts/check` | List, mark read, and run expiry checks. |
| `POST /api/plan`, `POST /api/plan/research` | Generate meals; the second accepts `{ "research": true }` to search Exa. |
| `POST /api/live/session`, `POST /api/live/delegate` | Create browser WebRTC signaling and execute controlled client delegation. |
| `POST /api/expiry/preview` | Simulate classifications for a date without changing the clock, database, or sending messages. |

## V1 test walkthrough

1. Under Supabase **Authentication → URL Configuration**, set the Site URL to the frontend origin and add `<origin>/login?confirmed=1` to Redirect URLs. Open the app, create an account, confirm your email, and sign in. If a link expires, choose **Need a new confirmation link?** on the login page to request another. Old links cannot be reused.
2. In **Add items**, select Food and enter or say: “Bought milk today, lasts two days, in the fridge.” Extract, review, fill in any missing fields, and confirm. Check the pantry and edit or mark the item used.
3. Select Household, add an object such as spare keys, its category and location, and confirm. Find it in Household and change its location.
4. In Alerts, choose **Check now** to create in-app reminders. Preview a future date without modifying data or sending messages.
5. Generate meals in Meal planner. Enable Exa for linked recipe inspiration and related photos within each card; food expiring within three days is prioritized. Images are related search results, not necessarily photos of the generated recipe.
6. Use a supported browser with HTTPS or localhost and grant microphone access to try a voice note and Live conversation. Install from your browser's app menu where supported.

Real SMS is enabled in the current workspace; WhatsApp remains disabled. The developer demo sends no real messages. Automated checks used temporary accounts that have been deleted.

## Notifications and operational limits

Each scheduled channel/slot is claimed once. A database write and external delivery cannot be made atomic; an interrupted or ambiguous SMS or WhatsApp send is marked unknown and is not blindly retried. `sent` means accepted by Twilio, not delivered to a device. Calls are simulated. Jobs more than 30 minutes late are skipped. If the Codespace or server stops, the worker stops and availability is not guaranteed.

Twilio's sandbox requires each recipient to join and sessions expire after three days. Free-form outbound messages require a customer service window started by a user message; business-initiated messages outside that window require approved templates. This implementation sends free-form messages and has no template fallback. See [Twilio sandbox documentation](https://www.twilio.com/docs/whatsapp/sandbox).

OpenAI models, network access, Supabase, and the web browser can fail independently. No automatic alternate AI provider, background queue, or offline data synchronization is configured. The documented 08:00 scheduler needs a running server; this POC does not guarantee high availability.

## Reference documentation

- [OpenAI live transcription](https://developers.openai.com/api/docs/guides/realtime-transcription)
- [OpenAI GPT-Live and client delegation](https://developers.openai.com/api/docs/guides/live-delegation)
- [Exa Search API](https://exa.ai/docs/reference/search)
- [Cerebras structured outputs](https://inference-docs.cerebras.ai/capabilities/structured-outputs)
- [shadcn/ui Next.js installation](https://ui.shadcn.com/docs/installation/next)
- `docs/KT_HANDOFF.md`: baseline architecture assessment and earlier handoff, retained as a historical snapshot.
