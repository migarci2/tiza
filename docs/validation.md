# Validation record

## Current verification — 11 September 2026, Oracle follow-up

- Python: **43 passed**, including the optional PostgreSQL test enabled against an isolated PostgreSQL 16 database. The only warning is an existing Starlette/AnyIO deprecation.
- PostgreSQL: blank-database migrations reached `b61e23a047df`; HTTP workflow, uniqueness, row locking, RLS and private table grants passed with Supabase-style `anon`/`authenticated` roles present. SQLite in the running Compose demo reached the same migration.
- Strands: the installed SDK, tool schemas, Agent loop, sequential executor, hooks and tool-result protocol run against a controlled offline `Model`. Tests cover empty/invalid selections, the twelve-call limit, successful handoff and rollback with retained failure traces. This does **not** verify Bedrock access or model quality.
- Browser: the cycle regression and landing/access regression both passed against `http://localhost:8086`. The cycle test completes Maya's approved path, preserves a changed exercise's branch, checks hint provenance, verifies the answered question stays visible until Continue, reviews a short response through the teacher UI and observes 1/8 completed in the brief. Landing checks include mobile layout and code access.
- Frontend: Vitest passed (one locale consistency test); TypeScript/Vite and Docker builds passed. Caddy validated the request body limit configuration.
- New regressions cover explicit English/Spanish objectives, honest source references, manual concept selection, retired exercise version preservation, corrected fraction questions, atomic daily admission and quotas surviving reset.

Live Bedrock, Supabase, Resend, public deployment and final Devpost submission remain unverified. The repository remains private by the owner's instruction. The updated submission draft is in `docs/hackathon/submission.md`. No educational efficacy or time savings have been measured.

The refreshed landing recording completes a learner path before returning to the teacher brief. Exported MP4: 45.60 seconds, 994,818 bytes; GIF: 4,197,060 bytes. Its agent sequence remains capture-only illustration and its manifest remains `model_invoked=false`.

## Historical checks before the Oracle follow-up


Local validation on 10 September 2026 used synthetic identities only.

Final results: `pytest` 23 passed, 1 skipped (the optional PostgreSQL test, separately executed successfully); PostgreSQL 1 passed; Vitest 1 passed; Playwright 2 passed; TypeScript/Vite and Docker builds passed. PostgreSQL migrations reached `d7c3b922a184`, with no pending Alembic operations. The running container demo uses http://localhost:8086 in this workspace (the default Compose port remains 8080).

* Python: API isolation, versioned approvals, attempt and hint provenance, grader/policy properties, original-JavaScript inference parity, cross-language signatures, consent, worker retries and mocked Strands tool boundaries.
* PostgreSQL: an isolated PostgreSQL 16.14 database was migrated and exercised through the same API routes, including uniqueness, row locking and private-table/RLS assertions. See [database validation](postgres-validation.md).
* Frontend: TypeScript/Vite build, Vitest and Playwright. Desktop and mobile images were compared with the generated design reference; see [design artifacts](design/).
* Containers: gateway, API, worker, beat, Redis and Mailpit all started successfully. `uv run python scripts/smoke.py --url http://localhost:8086` created a cycle through HTTP, waited for real Celery processing, approved/published 8 assignments, recorded a hinted answer, replayed it without duplication and reconstructed participation as 1 in progress / 7 not started. Mailpit accepted 8 messages; they remained `provider_accepted`, not `delivered`.

The smoke script only runs when the server reports demo mode. It advances the explicitly synthetic organization clock to daytime to exercise quiet-hour-aware notifications. It requires Mailpit and must not be pointed at a real classroom.

Bedrock, Supabase Auth/Storage and Resend are implemented as configurable adapters but have not been exercised against the user's live accounts. No real emails were sent. Mocked model tests verify tool constraints, not model quality. Exercise validation and a working administrative cycle do not establish educational effectiveness.

Landing/access update: desktop and 390px mobile reviewed against the generated access reference. Playwright verifies no quick-entry button, explicit local no-email status, incorrect-code rejection, valid-code entry at `/workspace`, and the complete reinforcement cycle. The first browser run encountered a stopped local API; after starting the API and worker, both tests passed.

11 September illustrated landing revision: Vite and Docker builds passed; both Playwright tests passed (full cycle plus desktop/mobile chapter navigation, code access and reduced-motion checks); Vitest passed. New artwork/font URLs return 200 from the running gateway. Browser screenshots are in `docs/design/story-hero-{desktop,mobile}.png` and `docs/design/story-practice-{desktop,mobile}.png`. No backend behavior changed in this revision.

11 September product-loop revision: the hero loop is a 28.64-second browser capture with a recording-only illustrated agent trace (no persisted or claimed real model invocation). MP4: 625,927 bytes; GIF: 2,704,673 bytes. The first 0.65 seconds of browser startup were trimmed. Playback, pause, reduced-motion behavior, GIF link, code access and the complete practice flow passed Playwright (2 tests). Python: 23 passed, 1 optional PostgreSQL skip; Vitest passed. Agent-run access is organization/class scoped, exposes an allowlist and distinguishes actual model metadata from deterministic work. Live Strands execution remains unverified pending account configuration.


11 September visual unification: Playwright verifies identical primary-action color and font between landing and workspace, the shared brand, and no horizontal overflow at 390px. The recording script checks each illustrated agent step becomes active in order and that drafts remain hidden until the sequence finishes. Vitest and both browser regressions pass; the regenerated media uses the shared design.


11 September media update: all character scenes use GPT Image raster assets. The clean video frame has decorative circles and a hover/focus/touch pause control; visible header/footer captions and download controls are removed. The Docker build, Vitest and both Playwright tests pass against `TIZA_TEST_URL=http://localhost:8086`. The recording checks the two-second illustrated agent stages and visible cursor coordinates for each interaction.


Demo-code access: the single-field form sends only `{code}` to `/api/auth/demo-code`. API regressions cover malformed and incorrect codes, no unauthenticated session, refusal of email login in demo mode and disabled demo access outside demo mode. Python: 23 passed, one optional PostgreSQL skip. Browser regressions cover no email field, wrong-code rejection, direct workspace entry and the complete reinforcement cycle.


The latest frontend pass preserves code-only access and the three teaching chapters, simplifies duplicate layout elements, and replaces the agent sparkle with the Practice planner notebook icon. TypeScript/Vite, Vitest and both browser regressions pass. The simplified illustrations were generated with GPT Image using the first scene as the style reference.
