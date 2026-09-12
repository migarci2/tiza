# Tiza — video treatment and narration

Updated 12 September 2026. Planning draft; no video has been rendered or submitted.

## Motion-design cut — proposed direction

**Target:** 2:15, 1920×1080, 30 fps, English voiceover and captions. Intended editor: Raylight. The longer narration below remains source material to shorten during a scratch voice read.

**Concept: The space between classes.** A yellow circle becomes a fraction, divides into eight pieces, follows individual practice paths and reunites at the next lesson. The pieces represent the eight synthetic learners, never grades or mastery.

Use the current app palette: paper #fffdf8, ink #252b38, blue #0866e6, yellow #ffda45, coral #ff927b and mint #d6ede2. Use Manrope, the Tiza wordmark and the unmodified official logo at `apps/web/public/brand/strands-agents.svg`. Reuse the simple GPT Image illustrations; generate any additional character or scene artwork with GPT Image. Typography and geometric transition masks remain editable editor layers.

| Time | Picture and motion | Main message |
| --- | --- | --- |
| 0:00–0:10 | Huge “Class dismissed.” lands on cream. A lesson sheet closes. Choose / Adapt / Check / Prepare arrive on successive beats. A yellow circle sweeps into the Tiza mark. | Class dismissed. Work continues. |
| 0:10–0:23 | Circle splits into eight pieces around a simple teacher illustration. They become learner markers; a camera push lands on the real classroom. | One class. Eight learners. |
| 0:23–0:38 | Real capture: objective, practice budget, deadline and concept confirmation. Frame the field or decision being discussed. | Set the goal. Confirm the scope. |
| 0:38–1:02 | Real connected preparation, completed tool events and two actual draft paths with their reasons. Introduce the Strands logo alongside the Practice agent panel. | Individual drafts, grounded in evidence. |
| 1:02–1:17 | Music drops. Hold on the exercise preview, version and recipients. Teacher approves and publishes; a crisp click releases the eight markers into their paths. | You approve what goes out. |
| 1:17–1:39 | Learner view: hint, objective answer, visible save confirmation and an already-approved branch. Show a short explanation awaiting teacher review. | Practice. Feedback. Evidence. |
| 1:39–1:56 | Teacher brief and supporting attempt. Hold the evidence long enough to read. Learner markers regroup around the next lesson. | Know where to begin next. |
| 1:56–2:07 | Architecture insert: Strands + Bedrock → scoped draft tools → teacher review. Backend below owns durable jobs, publication, grading and evidence. | AI plans. Teachers approve. Code checks. |
| 2:07–2:15 | Circle closes into the wordmark accent. Cream canvas, strong blue/yellow framing. Hold the final frame for three seconds. | You teach. Tiza handles the practice between classes. |

### Rhythm and sound

- Direction: 120 BPM instrumental, playful percussion, plucked notes and a firm bass pulse. Select music licensed for public YouTube/Vimeo use before locking the edit.
- Opening cuts every 1–2 seconds; product shots hold 4–7 seconds. Reframe quickly between readable holds. Keep UI flat while reading, with 3D tilt only on entrances or exits.
- Three recurring transitions: circle-mask reveal, match cut from exercise card to learner view, lateral camera move between learner paths.
- Use the existing natural macOS-style cursor treatment. Preserve actual interactions; no wandering pointer or decorative click rings.
- Restrained paper/click sounds, music ducked beneath narration, a short near-silence at approval. Captions use two lines maximum and stay clear of important UI.

### Production order and pending footage

1. Design three keyframes: opening, agent/draft comparison and closing. Reuse existing brand assets.
2. Record a scratch English narration from the source below. Shorten it to fit these beats, leaving pauses to read the interface.
3. Assemble opening and closing in Raylight, with placeholders for real captures. Confirm supported media imports and export settings in the editor before building the full timeline.
4. After AWS account verification, validate the real Strands run. Current candidate: `eu.amazon.nova-2-lite-v1:0`, region `eu-central-1`. Inference is currently blocked by account verification; this model is not yet validated end to end.
5. Record one connected synthetic cycle and retain a redacted run trace. Capture actual draft differences, approval, practice and the resulting brief. Use only the figures produced by that recording.
6. Replace placeholders, finish licensed audio and captions, export, then review readability at laptop size.

The landing GIF/MP4 contains an illustrated agent sequence and is not proof of a connected run. The final video must use actual completed tool events. Identify synthetic learners in narration and the classroom view; do not claim measured time savings, learning gains, real email delivery or deployment on AgentCore. Any shortened wait uses an explicit edit, not an invented duration.

The [official hackathon overview](https://agentsforhumans.devpost.com/) asks for a working-project demonstration and a pitch covering the problem, audience and significance, within five minutes. This treatment targets Professional Agents. [Raylight](https://www.raylight.app/) advertises product-screen layers, camera moves, animation blocks and audio tools suited to this direction. Both sources checked 12 September 2026. No Raylight upload, purchase or public video publication has been performed.

## Longer narration source — English

Target: 2–3 minutes. Record only after connecting and verifying the real Strands run. No narration below claims measured educational impact.

**0:00–0:20 — Problem and audience**
“Private tutors don't stop working when a lesson ends. They still choose practice, adapt it for different learners, check answers and decide where the next lesson should begin. Tiza takes on that between-class cycle.”

**0:20–0:45 — The teacher sets the boundary**
Show the synthetic fractions classroom, lesson goal, material references, concept confirmation, time budget and deadline. “The teacher defines the goal and confirms the topic. Tiza works within those boundaries.”

**0:45–1:20 — The agent does real work**
Run the connected Strands agent. Show recorded tool calls, validated exercise selection and two different learner drafts. “The agent reads this cycle's context, selects from reviewed activities, saves individual drafts and returns for one human decision.” Expand the actual run trace; do not replace failed provider calls with successful-looking animation.

**1:20–1:45 — Approval and publication**
Review the version and publish it. “Approval is tied to this exact content and these recipients. Editing the plan invalidates that approval.” Show assignments becoming available. Distinguish provider acceptance from delivered email.

**1:45–2:10 — Practice and evidence**
Switch explicitly to a synthetic learner, request a hint and answer. “Objective answers are checked on the server. Help is recorded, and uncertain explanations go back to the teacher.”

**2:10–2:35 — Next class prepared**
Open the brief and its supporting attempt. “The next class starts with a clear view of who responded, which answers deserve a second look and what is still unknown.”

**2:35–2:50 — Architecture and close**
Briefly show `architecture.md`. “Strands handles bounded planning. Durable jobs, permissions, grading and publication live in the service. Tiza doesn't replace your class. It takes care of the work between one class and the next.”

End with the real repo URL and test instructions once available. Declare synthetic identities and any simulated time. This script is prepared material, not a published or submitted video.
