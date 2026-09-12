# Tiza architecture

```mermaid
flowchart LR
  T[Teacher: goal, concepts, approval] --> W[React workspace]
  L[Learner: answers and hint requests] --> W
  W --> API[FastAPI: session, CSRF, class permissions]
  API --> DB[(Local SQLite and tested PostgreSQL)]
  API --> J[Transactional job and outbox]
  J --> Q[Redis and Celery worker]
  Q --> P[Reviewed-exercise policy]
  P --> D[Teacher-review drafts]
  D --> API
  API --> G[Server grading and evidence revisions]
  G --> DB
  DB --> B[Lesson brief with supporting attempts]

  Q -. connected planning path .-> A[Strands SDK: integration tested offline]
  A --> D
  A -. live call not verified here .-> M[Amazon Bedrock]
  API -. configured, not verified here .-> S[Supabase Auth and private Storage]
  Q -. configured, not verified here .-> E[Resend]
```

## Verified local path

The local synthetic workflow runs React/Vite, FastAPI, a durable job/outbox path, the reviewed fractions catalog, deterministic planning, version-bound teacher approval, server-side grading and evidence-backed lesson briefs. In `deterministic_demo`, preparation writes `model_invoked=false`; the interface and persisted metadata identify it as a local run. The landing preview is a recording of that synthetic workflow with an illustrative, capture-only tool sequence. Its manifest preserves that no model was invoked.

The teacher authorizes the exact version before publication. The agent path cannot approve, publish, submit learner answers, write grades or execute arbitrary database work. Its scoped tools read cycle context and validated candidates, save bounded draft choices, and request teacher review.

## Deployment and provider path — unverified here

The production configuration is designed to use PostgreSQL, Redis/Celery, Strands with Bedrock, Supabase Auth/private Storage, Resend and HTTPS behind Caddy. Those provider integrations require credentials and an account configuration outside this workspace. They have not been exercised here, so the dashed links in the diagram are architectural integrations, not a claim of a connected run, delivery, deployment or provider audit.

Use [submission.md](submission.md) to run and record a connected cycle. Inspect the persisted agent run rather than inferring a model invocation from UI motion or a local preview.
