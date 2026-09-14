<div align="center">
  <h1>tiza: Practice between classes</h1>
  <p>Turn one lesson into individual practice, teacher-reviewed feedback and a clearer starting point for the next class.</p>
  <p><a href="https://tiza.migarci2.dev/">Try it online</a> · <a href="#run-locally">Run it locally</a> · <a href="docs/judge-guide.md">Follow the demo</a></p>
</div>

<div align="center">
  <img src="./data/landing.gif" alt="Tiza product walkthrough" width="100%">
</div>

## Make the time between lessons count

A class ends, but the teacher's work does not. They still need to choose useful exercises, adjust them for different learners, check the answers and decide what to revisit next time.

**Tiza brings that work into one simple cycle.** The teacher sets the goal and time limit. Tiza prepares an individual practice plan for each learner from reviewed exercises. The teacher checks the plans and approves the exact version before anything is published.

As learners practise, Tiza records their answers, hints and pending reviews. The next-lesson brief shows the teacher what happened and links every observation to the work behind it.

## One lesson, three clear steps

1. **Choose the goal.** Add the lesson material, select the concepts and set how long practice should take.
2. **Review the practice.** Compare each learner's plan, change exercises or recipients, then approve the exact version.
3. **Start the next class prepared.** See who responded, what needs review and the attempts behind each observation.

The learner gets a focused mobile practice flow. The teacher keeps control of what is sent and how the results are used.

## Simple for the teacher. Careful behind the scenes.

| What Tiza handles | Why it matters |
| --- | --- |
| Individual plans from reviewed exercises | Each learner gets a useful path without giving the agent an open-ended content generator. |
| Approval tied to one exact version | A change to the plan requires a new teacher decision. |
| Server-checked objective answers | Results do not depend on a model deciding whether an answer is correct. |
| Hints and explanations kept with each attempt | The teacher can see the context behind an answer. |
| A brief linked to the original work | Every next-lesson observation can be checked. |
| Durable jobs and delivery records | Preparation and sending can recover without losing their history. |

The demo uses eight fictional learners and a reviewed fractions exercise bank. It does not claim official grades or measured learning results.

## Human approval is part of the product

Tiza uses a bounded Strands agent to prepare practice plans. It can read the current class goal, choose from available exercises, save drafts and request review. It cannot approve a plan, publish it, submit learner answers or write directly to learning records.

Editing a plan creates a new version and clears the previous approval. Completed attempts stay attached to the version the learner actually received.

## Run locally

Requirements: Python 3.12+, Node.js 22+, [uv](https://docs.astral.sh/uv/) and [pnpm](https://pnpm.io/).

```sh
./scripts/dev.sh
```

Open [http://localhost:5173](http://localhost:5173) and enter demo code `246810`. No account or provider credentials are needed for the default walkthrough. The interface clearly marks local preparation when no AI model was called.

API documentation is available at [http://localhost:8000/docs](http://localhost:8000/docs).

## Container demo

```sh
cp .env.example .env
docker compose --profile demo up --build
```

Open [http://localhost:8080](http://localhost:8080). Mailpit is available at [http://localhost:8025](http://localhost:8025) for local email testing.

The demo uses SQLite so it can run on its own. A connected deployment uses PostgreSQL, Supabase Auth and Storage, Bedrock through Strands, and optional Resend delivery. See [.env.example](.env.example) for the full configuration.

Run migrations before starting a connected deployment:

```sh
uv run alembic upgrade head
```

## Reliability checks

```sh
uv run pytest -q
pnpm --dir apps/web build
pnpm --dir apps/web test
pnpm --dir apps/web test:e2e
```

The smallest container smoke check is:

```sh
uv run python scripts/smoke.py --url http://localhost:8080
```

See the [validation record](docs/validation.md) for the verified scope and the limits of offline testing.

## Project guide

- [Architecture](docs/architecture.md)
- [Demo walkthrough](docs/judge-guide.md)
- [Validation record](docs/validation.md)
- [Privacy and operations](docs/privacy.md)

## Safety boundary

Tiza keeps planning separate from approval, publication and grading. Production use requires HTTPS, secure cookies, private storage, a managed PostgreSQL backup policy and provider credentials kept outside Git.

Built for the **Professional Agents** track of Agents for Humans. MIT licensed; see [LICENSE](LICENSE).
