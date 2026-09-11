# Tiza HTTP contract (MVP)

All JSON routes live under `/api`. Browser sessions use the HttpOnly cookie
`tiza_session`. Every successful login/session response also returns `csrf_token`;
send it as `X-CSRF-Token` on `POST`, `PATCH`, `PUT`, and `DELETE` requests. Errors are
`{"detail": "human readable message"}`.

## Access code, demo and session

- `POST /demo/session` always returns `410`; direct unauthenticated demo entry has been
  removed. Demo users enter through the access-code routes below.
- `GET /session` returns the same session shape.
- `GET /config` -> `{demo_mode, agent_mode:"deterministic_demo"|"bedrock"}`.
- `POST /demo/switch` body `{"user_id": "..."}`. The teacher id switches back to the
  teacher; an enrolled synthetic learner id opens that learner's authorized view.
  Returns the session shape with `role: "learner"` when acting as a learner.
- `POST /demo/reset` body `{}` removes demo cycles/attempts and restores the reviewed
  fraction bank and eight synthetic learners. Returns the teacher session shape.
- `POST /auth/demo-code` body `{code}` -> session shape for the synthetic teacher.
  Default demo code: `246810`, configurable through `TIZA_DEMO_ACCESS_CODE`. No email
  field or request-code step. Returns `401` for an invalid code, `422` for malformed
  input and `404` when demo mode is disabled.
- `POST /auth/request-code` and `POST /auth/verify-code` remain backend Supabase
  identity endpoints for non-demo deployments. They return `400` in demo mode;
  the current demo interface does not expose an email sign-in flow.
- `POST /auth/logout` body `{}` -> `204`.

The session shape also contains `agent_mode`. `User` is
`{id, email, display_name, synthetic}`.

- `GET /workspace` -> `{id, name, timezone}`.
- `PATCH /workspace` body `{timezone}` -> the same shape. Timezone must be an IANA
  name such as `Europe/Madrid`. Session responses also include `timezone`.

## Teacher workspace

- `GET /dashboard` -> `{classroom: Classroom, active_cycle: Cycle|null,
  pending_approval: Cycle[], decisions: [{kind, label, cycle_id}]}`.
- `GET /classrooms` -> `Classroom[]`.
- `GET /classrooms/{id}` -> `{...Classroom, learners: User[], cycles: Cycle[]}`.
- `POST /classrooms` body `{title, language:"en", practice_minutes:15}` -> Classroom.
- `POST /classrooms/{id}/invitations` body `{email}` ->
  `{id, email, expires_at, invite_token}`. The raw token is returned once.
- `GET /exercises/catalog` (teacher only) -> approved exercise objects including
  `{id, concept_id, kind, prompt, options, answer, explanation, hint,
  estimated_minutes, source}` for the review editor.

`Classroom` is `{id, title, language, practice_minutes}`. `Cycle` is
`{id, classroom_id, objective, concepts:string[], closes_at, budget_minutes, state,
version}`.

## Cycle

- `POST /cycles` body `{classroom_id, objective, concepts?:string[], closes_at,
  budget_minutes}` -> Cycle.
- `POST /cycles/{id}/materials` multipart field `file` (`.txt`, `.md`, text-layer
  `.pdf`, max 10 MB/30 pages) -> `{id, filename, sha256, page_count, status,
  excerpt, concept_candidates:[{id,title,reference}]}`.
- `POST /cycles/{id}/concepts` body `{concept_ids:string[]}` -> Cycle. Preparation is
  rejected until this teacher confirmation exists.
- `POST /cycles/{id}/prepare` body `{}` -> `{job_id, state:"queued",
  cycle_state:"preparing"}`. Preparation is a persistent job. Poll its SSE endpoint
  or the draft; the demo worker executes the same domain entrypoint as production.
- `GET /cycles/{id}/draft` -> `{cycle: Cycle, assignments: DraftAssignment[]}`.
- `PATCH /cycles/{id}/draft` body
  `{version, assignments:[{id, excluded?:boolean, exercise_ids?:string[]}]}` -> the full draft.
  A real change increments `cycle.version` and invalidates any prior approval.
- `PATCH /cycles/{id}` body `{version, closes_at}` -> Cycle. Changing the deadline
  creates a new immutable draft version and invalidates the prior approval.
- `POST /cycles/{id}/approve` body `{version, assignment_ids,
  allow_reminder?:boolean}` -> `{id, version, batch_hash, recipient_ids,
  permissions, created_at}`.
- `POST /cycles/{id}/publish` body `{approval_id, version}` ->
  `{cycle: Cycle, assignments:[{id, learner_id, state, published}],
  deliveries:[{id, assignment_id, state}]}`. Approval version, recipients, and the
  current batch hash are rechecked. Repeating the call does not duplicate deliveries.
- `GET /cycles/{id}/brief` -> `{cycle_id, completion:{total, completed,
  in_progress, not_started, review_needed}, patterns:[{text, attempt_ids}],
  missing_learners:User[], opening_activity:{title, reason}|null}`.

`DraftAssignment` is `{id, learner:User, version, reason, estimated_minutes, state,
excluded, items:DraftItem[]}`. `DraftItem` is `{id, position, branch_after_item_id,
branch_on, exercise:{id, concept_id, kind, prompt, options,
estimated_minutes, source}}`. Answers are never returned.

For multiple choice, `options` is `[{id, text}]`; submit the chosen option `id`.

## Learner practice and teacher review

- `GET /assignments` -> `[{id, cycle_id, learner_id, state}]`, scoped to the active
  learner or to the teacher's organization.
- `GET /assignments/{id}` -> `{id, cycle:{id, objective, closes_at}, learner:User,
  state, progress:{answered,total}, items:PracticeItem[]}`. A learner can only read
  their own published assignment. A teacher in the organization can preview it.
- `POST /assignments/{id}/items/{item_id}/hint` body `{}` -> `{event_id, hint}`.
  Requesting it is persisted immediately, even if the learner never submits.
- `POST /assignments/{id}/attempts` body `{item_id, response,
  client_key}` -> `{id, item_id, result:"correct"|"incorrect"|"review_needed",
  score:number|null, feedback, explanation, used_hint, submitted_at}`. Repeating `client_key`
  returns the original attempt and produces no new evidence.
- `POST /attempts/{id}/review` body `{outcome:"correct"|"incorrect", feedback}` ->
  `{attempt_id, result, evidence_event_id, revision}`. Teacher only; history is
  appended and the previous evidence is superseded.
- `GET /attempts/{id}` -> `{id, learner, question, response, result, used_hint,
  submitted_at, revisions:[{id,outcome,evaluator,revision,created_at}]}`, scoped to
  the owning learner or classroom teacher.
- `GET /cycles/{id}/pending-reviews` -> `string[]` of review-needed attempt IDs for
  the classroom teacher.

`PracticeItem` contains the same fields as `DraftItem`, plus `attempt` when answered.
It never contains the verifier answer. Branch items remain hidden until their approved
condition is reached.

## Operational

- `GET /health` -> `{status:"ok"}`.
- `GET /runs/{job_id}/events` is an SSE stream ending with
  `event: status\ndata: {"state":"completed"}\n\n` for a visible job.
- `Idempotency-Key` is accepted on publish; attempt idempotency uses `client_key`.
