# PostgreSQL validation

The optional test at `tests/postgres/test_postgres_flow.py` runs only when
`TIZA_TEST_POSTGRES_URL` points to an isolated database whose Alembic migrations
have already been applied. It uses the application HTTP routes for cycle
creation, preparation, approval, publication and learner submission. It also
checks PostgreSQL's attempt uniqueness constraint and `FOR UPDATE SKIP LOCKED`
behavior on a delivery row.

On 10 September 2026 it passed against PostgreSQL 16.14 using image
`postgres@sha256:081f1bc7bd5e143dbb6e487b710bbc27712cdcfaced4c071b8e47349aa1b4171`.
Alembic upgraded a blank database to `d7c3b922a184 (head)` and the test completed
with `1 passed`. A second run created Supabase-style `anon` and `authenticated`
roles before migration: all 23 private application tables had RLS enabled, none
had grants to `anon`, `authenticated`, or `PUBLIC`, and the full API flow still
passed. The database contained synthetic demo identities only and its disposable
container was removed after the run.

Example local invocation:

```sh
TIZA_DATABASE_URL="$TIZA_TEST_POSTGRES_URL" uv run alembic upgrade head
uv run pytest tests/postgres/test_postgres_flow.py -q
```
