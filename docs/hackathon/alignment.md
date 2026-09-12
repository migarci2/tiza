# Agents for Humans — Tiza alignment

Checked 11 September 2026 against the [official overview](https://agentsforhumans.devpost.com/) and [official rules](https://agentsforhumans.devpost.com/rules).

**Track: Professional Agents.** Tiza takes on a tutor's between-class practice workflow: scoped planning, a teacher review boundary, publication, learner responses and a lesson brief. The teacher defines the goal, confirms concepts and approves the exact version before anything is published.

## Official submission facts

The rules list a submission deadline of **14 September 2026, 5:00 pm Pacific** (15 September, 02:00 in Europe/Madrid). A submission needs an English project description, an architecture diagram, an AWS Builder ID, a public YouTube or Vimeo video of at most five minutes that demonstrates and pitches the project, and access for judging/testing. The rules also require a new project built with Strands Agents, a public GitHub/GitLab/Bitbucket repository with source, assets, instructions, README and a visible MIT or Apache license. A live demo is optional but may help technical-implementation scoring. See the [rules](https://agentsforhumans.devpost.com/rules).

The repository remote is [github.com/migarci2/tiza](https://github.com/migarci2/tiza). It is intentionally private at the owner's request. That choice is preserved here; it does not meet the rules' public-repository requirement, so a submission should not claim that requirement is complete while the repository remains private.

## Evidence in this workspace

| Area | Current position |
| --- | --- |
| Product workflow | Local synthetic teacher → review → learner → evidence → lesson-brief workflow exists, with API, unit and browser checks. |
| Agent boundary | The code has a Strands/Bedrock path with four scoped tools. Approval, publication, grading and evidence remain service-owned. |
| Local agent run | `deterministic_demo` is a local policy run and records `model_invoked=false`. It is not evidence of a Bedrock invocation. |
| Illustrative preview | The landing media records a real synthetic browser path. Its illustrated tool sequence is capture-only; the media manifest records `agent_trace_illustrated=true` and `model_invoked=false`. |
| Connected providers | Bedrock, Supabase, Resend, AWS credentials and public deployment have not been verified from this workspace. Do not claim a live AWS run, provider delivery, measured learning outcomes, time savings or an exhaustive audit. |
| Reuse | The nema-derived interoperability work and the visual assets have documented attribution in the repository. |

## Before submitting

1. Run and retain evidence from a connected Bedrock cycle using the instructions in [submission.md](submission.md). Confirm the persisted agent run says `mode: bedrock` and `model_invoked: true`.
2. Record the working connected path, then publish the final English video to YouTube or Vimeo. The landing preview is not a substitute for that proof.
3. Decide how to satisfy the public-source requirement without changing the owner's private-repository preference unintentionally. Add the actual public URL only after that decision.
4. Add the participant's AWS Builder ID, testing URL or test-build access, and any required credentials to the Devpost form. Keep secrets out of the repository.
5. Disclose pre-existing code or work incorporated into the project as required by the rules.

## Demonstration emphasis

Show the delegated task, the teacher's approval, the resulting learner work and the supporting evidence. Describe synthetic records as synthetic. A response pattern is an observation for the next lesson, not a diagnosis.
