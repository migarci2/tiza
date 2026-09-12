# Devpost submission draft — English

Use this as source material for the Devpost form after the connected run, public-source decision and final video are complete. It is a draft, not a submitted entry.

## Short description

Paste this unchanged for the 190-character field in `DEVPOST_SUBMISSION.md`:

> Tiza helps tutors turn lesson goals into individual practice. You review and approve; the agent assigns exercises, checks answers, and summarizes results to help you prepare the next lesson.

## Project name

Tiza — reviewed practice between classes

## Description

Tiza is a workspace for independent tutors and small classes who need to turn one lesson into useful practice before the next one. A teacher records a narrow goal, confirms the concepts in scope and sets a short practice budget. Tiza prepares individual exercise drafts from a reviewed fractions bank. The teacher reviews the exact drafts, can edit or exclude them, then approves and publishes that version.

Learners receive one exercise at a time. The service records hints separately from answers. Objective items are graded on the server; short explanations are held for teacher review. The next-lesson brief links participation and observed response patterns back to the attempts that support them, while leaving unanswered work separate from incorrect work.

The connected agent path uses Strands Agents with Amazon Bedrock for bounded draft preparation. It receives only the authorized cycle context, limited material excerpts and validated candidate exercises. Its four tools read that context, inspect candidate exercises, save scoped draft choices and request teacher review. It cannot approve or publish a plan, submit learner answers, alter grades or add unreviewed exercises. FastAPI services retain authorization, version checks, grading, evidence revision and delivery state.

The included local demo uses synthetic identities and deterministic planning. It records `model_invoked=false` and should not be presented as a Bedrock run. The landing preview is an illustrative recording of a synthetic browser workflow; its capture-only tool sequence is documented in the media manifest and is not persisted as an agent run. Tiza does not claim measured learning gains, time savings or educational diagnosis.

## Built with

- Strands Agents SDK and Amazon Bedrock for the connected planning path
- FastAPI, SQLAlchemy and Alembic
- React, TypeScript, Vite and TanStack Query
- PostgreSQL, Redis/Celery, Supabase Auth/private Storage and Resend in the configured deployment architecture
- A reviewed 12-concept fractions catalog and server-side deterministic grading

## Repository, video and testing fields

Fill these fields only with completed, accessible artifacts:

| Field | Value to provide |
| --- | --- |
| Source code | The public repository URL once the owner decides to make a submission copy public. The current repository remote is private: `https://github.com/migarci2/tiza`. |
| Demo video | Public YouTube or Vimeo URL for the final English video, at most five minutes. |
| Testing access | A working URL or test build, login/testing instructions and any judge credentials needed during the judging period. |
| AWS Builder ID | Participant-provided Builder ID. |
| Architecture diagram | `docs/hackathon/architecture.md` or a rendered copy of its Mermaid diagram. |

## Connected-run checklist

Do this in an authorized AWS and provider account; do not commit the resulting `.env`, credentials or recordings containing real learner data.

1. Keep `TIZA_DEMO_MODE=true` and code-only access with eight synthetic learners. Set `TIZA_AGENT_MODE=bedrock`, `TIZA_BEDROCK_MODEL_ID` and `AWS_REGION` for a model tested in the authorized account. Make AWS credentials available to the worker, preferably through an instance role. SQLite/PostgreSQL and Mailpit can remain in place; Supabase and Resend are not prerequisites for this connected agent check. On a shared HTTPS judging instance, set `TIZA_SESSION_SECURE=true`, `TIZA_SITE_ADDRESS`, `TIZA_PUBLIC_URL` and `TIZA_DEMO_RESET_ENABLED=false`. Use a separate capture instance with reset enabled for the recording script.
2. Apply migrations with `uv run alembic upgrade head`, then start the configured API, worker, beat, Redis and gateway. The repository Compose source is `compose.yaml`; its API command also runs migrations. Use a controlled HTTPS environment for connected access.
3. Create a cycle through the workspace. Confirm concepts, queue preparation, wait for completion and open the cycle's agent activity. Verify the persisted run reports `mode: bedrock`, `model_invoked: true`, the configured model identifier, bounded model-call count and completed tool events. Capture those facts from `/api/cycles/{cycle_id}/agent-run` or the UI trace.
4. Review and publish the exact draft version. Use synthetic or consented test accounts, then confirm learner access, a hint event, an objective response and a teacher-reviewed short response. Check the lesson brief links back to the attempts.
5. Preserve a redacted run record, the repository revision, configuration identifiers without secrets, and the final video source. If the Bedrock run fails or says `model_invoked: false`, fix it or describe the run accurately; do not substitute the illustrative preview as evidence.

## Recording instructions

For the final Devpost video, record the connected run above and follow the sequence in [pitch.md](pitch.md). Narrate only what the screen and persisted run record show. Include the problem, intended users, why the workflow matters, the actual agent trace, teacher approval, learner evidence and the final brief. Use synthetic or consented data.

The repository also contains a local product-preview recorder:

```sh
cd apps/web
TIZA_CAPTURE_URL=http://127.0.0.1:5173 pnpm exec node scripts/record-demo.mjs
cd ../..
uv run python scripts/export_demo.py
```

`apps/web/scripts/record-demo.mjs` only accepts synthetic demo mode. With `TIZA_SIMULATE_AGENT=1`, it adds a capture-only illustrative tool sequence for the landing preview; `scripts/export_demo.py` exports the raw Playwright capture to `apps/web/public/media/`. The manifest at `apps/web/public/media/tiza-demo.json` records that this preview has `model_invoked=false`. It is suitable for the product page, not proof of a connected Bedrock run.

For a synthetic deployment smoke check, use:

```sh
uv run python scripts/smoke.py --url http://localhost:8080
```

That script refuses a non-demo server and uses synthetic records plus Mailpit. It does not verify Bedrock, Supabase, Resend or public deployment.
