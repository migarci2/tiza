# Agents for Humans — Tiza alignment

Checked 11 September 2026 against the [official overview](https://agentsforhumans.devpost.com/) and [rules](https://agentsforhumans.devpost.com/rules).

**Track: Professional Agents.** Tiza delegates the tutor's repeated between-class work: individual practice plans, approved publication, objective grading and a lesson brief. Human judgement stays at the approval and review boundaries.

## Required submission

The rules require a new Strands project, public MIT/Apache repository with runnable code and README, architecture diagram, English description, public YouTube/Vimeo demonstration of at most five minutes, AWS Builder ID and testing access. Prior work must be disclosed. AgentCore and a public AWS Builder post are optional. Deadline: 14 September 2026, 17:00 PDT (15 September, 02:00 Europe/Madrid). [Rules](https://agentsforhumans.devpost.com/rules)

## What is concrete now

- Working teacher → approval → learner → evidence → next-class flow, with browser regression.
- Strands runner with four scoped tools and a bounded Bedrock model call budget. The model can choose validated candidates and explain the selection. Domain services enforce every write and preserve approval boundaries.
- Agent activity panel reads persisted job metadata; it never turns a local policy run into an alleged model invocation.
- MIT license, third-party notices, setup instructions and architecture diagram are in the repository.
- New Tiza workflow and frontend; nema port and Yuvo visual influence are disclosed. Original Tiza illustrations and Manrope notices are included.
- Landing loop records synthetic browser interactions with an illustrative agent tool sequence, as requested. This visual-only sequence is identified in the accessible video description and media manifest and is not persisted as a real Strands run.

## Still required before calling the entry complete

| Item | Current evidence / remaining action |
| --- | --- |
| Real Strands/Bedrock execution | No AWS profile, credentials file or model ID is configured here. Configure an authorized account/model, run the full cycle and rerecord. Unit tests with mock models are not evidence of a live model call. |
| Public repository | No Git remote exists. Publish the prepared repository with its MIT license and record its URL. |
| AWS Builder ID | Participant-provided field; not available in the workspace. |
| Submission video | The landing loop is a short product preview, not the final pitch. Use `pitch.md`, record the connected workflow, then publish the final ≤5-minute video. |
| Testing access | Local code `246810` is only for synthetic local mode. Provide a working build or stable deployment and access instructions for judges. |
| Live deployment | Docker works locally; EC2/Supabase/Bedrock account deployment has not been executed. Do not describe localhost as a public live demo. |
| Eligibility and registration | Participant must complete their own registration and confirm eligibility; no submission was made. |

## Demonstration emphasis

Show the repetitive work that was delegated, the exact human decision, the completed side effects, and the trace behind the result. The teacher is the beneficiary; the trace is evidence, not the main product. Do not claim measured time savings, learning gains or a confirmed misconception from one answer. Do not describe the deterministic local recording as autonomous AI.
