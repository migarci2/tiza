# Tiza architecture

```mermaid
flowchart LR
  T[Teacher: goal and approval] --> W[React workspace]
  L[Learner: own answers] --> W
  W --> API[FastAPI: session, CSRF and class permissions]
  API --> DB[(PostgreSQL: versions, approvals, attempts, evidence, jobs)]
  API --> S[Supabase Auth and private Storage]
  DB --> O[Transactional outbox]
  O --> R[Redis / Celery]
  R --> WK[Worker: revalidate scope and version]
  WK --> A[Strands agent]
  A --> B[Amazon Bedrock model]
  A --> TOOLS[Read scoped context / choose valid candidates / save draft / request review]
  TOOLS --> DB
  WK --> MAIL[Resend: persistent delivery status]
  API --> G[Fraction grading and evidence revision]
  G --> DB
  DB --> BRIEF[Deterministic figures and supporting attempts]
  BRIEF --> API
  N[Optional consented nema assertion] --> API
```

The model cannot approve or publish. The authenticated teacher grants an immutable approval; the publication service and worker validate it before effects. The local preview substitutes SQLite and deterministic planning and labels that substitution. Actual model invocation and tool names are exposed only from persisted run metadata. EC2/Caddy deployment and external providers require account configuration.
