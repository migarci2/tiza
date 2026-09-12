import { chromium, expect } from "@playwright/test";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
const baseURL = process.env.TIZA_CAPTURE_URL || "http://127.0.0.1:5173";
const out = resolve("../../data/recordings");
const simulateAgent = process.env.TIZA_SIMULATE_AGENT === "1";
const illustratedTools = [
  "read_cycle_context",
  "select_validated_exercises",
  "save_assignment_draft",
  "request_teacher_review",
];
await mkdir(out, { recursive: true });
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  baseURL,
  viewport: { width: 1280, height: 800 },
  recordVideo: { dir: out, size: { width: 1280, height: 800 } },
  reducedMotion: "reduce",
});
const config = await (await context.request.get("/api/config")).json();
if (!config.demo_mode)
  throw new Error("Recording script is limited to synthetic demo mode.");
const session = await (
  await context.request.post("/api/auth/demo-code", {
    data: { code: "246810" },
  })
).json();
const reset = await context.request.post("/api/demo/reset", {
  headers: { "X-CSRF-Token": session.csrf_token },
});
if (!reset.ok()) throw new Error("Could not reset synthetic workspace");
// Capture-only pacing: no simulated progress is written to the server.
const stageDuration = 2000;
let previewStarted;
const previewStage = () =>
  previewStarted === undefined
    ? -1
    : Math.min(
        4,
        Math.floor((performance.now() - previewStarted) / stageDuration),
      );
if (simulateAgent) {
  await context.route("**/api/cycles/*/prepare", async (route) => {
    const response = await route.fetch();
    if (response.ok()) previewStarted = performance.now();
    await route.fulfill({ response });
  });
  await context.route("**/api/cycles/*/draft", async (route) => {
    if (previewStage() >= 0 && previewStage() < 4) {
      return route.fulfill({
        status: 409,
        json: { detail: "Preparing practice" },
      });
    }
    await route.continue();
  });
  await context.route("**/api/cycles/*/agent-run", async (route) => {
    const response = await route.fetch();
    const actual = await response.json();
    const stage = previewStage();
    if (
      stage < 0 ||
      actual.state === "failed" ||
      (stage === 4 && actual.state !== "completed")
    )
      return route.fulfill({ response });
    await route.fulfill({
      response,
      json: {
        ...actual,
        state: stage < 4 ? "running" : actual.state,
        mode: "illustrative_preview",
        model_invoked: false,
        model: null,
        model_calls: 0,
        draft_count: stage < 3 ? 0 : actual.draft_count,
        tools: illustratedTools.slice(0, stage),
        active_tool: illustratedTools[stage],
      },
    });
  });
}
// Browser video omits the system cursor; this capture-only overlay follows real mouse events.
const cursorAssets = await Promise.all(
  ["macos-cursor.svg", "macos-text-cursor.svg"].map(
    async (name) =>
      "data:image/svg+xml;base64," +
      (await readFile(new URL(`./assets/${name}`, import.meta.url))).toString(
        "base64",
      ),
  ),
);
await context.addInitScript(([arrow, text]) => {
  document.addEventListener("DOMContentLoaded", () => {
    const style = document.createElement("style");
    style.textContent = `
      #capture-cursor { position:fixed; left:0; top:0; width:48px; height:48px; z-index:2147483647; pointer-events:none; transform:translate(1100px,830px); }
      #capture-cursor img { position:absolute; top:0; left:0; width:48px; height:48px; transform:translate(-15px,-10.5px); filter:drop-shadow(0 1px 1px #0004); }
      #capture-cursor .text-cursor { width:40px; height:40px; transform:translate(-21px,-19px); display:none; }
      #capture-cursor[data-text] .arrow-cursor { display:none; }
      #capture-cursor[data-text] .text-cursor { display:block; }
    `;
    const cursor = document.createElement("div");
    cursor.id = "capture-cursor";
    cursor.setAttribute("aria-hidden", "true");
    cursor.innerHTML = `<img class="arrow-cursor" src="${arrow}" alt=""><img class="text-cursor" src="${text}" alt="">`;
    document.head.append(style);
    document.body.append(cursor);
    document.addEventListener("mousemove", (event) => {
      cursor.style.transform = `translate(${event.clientX}px, ${event.clientY}px)`;
      const target = event.target;
      cursor.toggleAttribute(
        "data-text",
        target instanceof Element &&
          (getComputedStyle(target).cursor === "text" ||
            target.matches(
              "textarea, input:not([type=file]):not([type=checkbox]):not([type=radio])",
            )),
      );
    });
  });
}, cursorAssets);
const page = await context.newPage();
// Dwell times pace a genuine browser recording. They do not change application progress or data.
const hold = (ms = 1800) => page.waitForTimeout(ms);
let pointer = { x: 1100, y: 830 };
const click = async (locator) => {
  await locator.scrollIntoViewIfNeeded();
  const box = await locator.boundingBox();
  if (!box) throw new Error("Recording target is not visible");
  const target = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  const start = pointer;
  const distance = Math.hypot(target.x - start.x, target.y - start.y);
  const steps = Math.ceil(Math.min(550, Math.max(180, distance * 0.55)) / 16);
  for (let step = 1; step <= steps; step++) {
    const progress = step / steps;
    const eased = 1 - Math.pow(1 - progress, 3);
    await page.mouse.move(
      start.x + (target.x - start.x) * eased,
      start.y + (target.y - start.y) * eased,
    );
    await hold(16);
  }
  pointer = target;
  await hold(90);
  await locator.click({ delay: 70 });
  const cursor = await page.locator("#capture-cursor").boundingBox();
  expect(Math.abs(cursor.x - target.x)).toBeLessThan(2);
  expect(Math.abs(cursor.y - target.y)).toBeLessThan(2);
};
let cycleId;
page.on("response", async (response) => {
  if (
    response.request().method() === "POST" &&
    new URL(response.url()).pathname === "/api/cycles" &&
    response.ok()
  )
    cycleId = (await response.json()).id;
});
try {
  await page.goto("/workspace");
  await page
    .getByRole("heading", { name: /Practice between classes/ })
    .waitFor();
  await hold(1800);
  await click(
    page.getByRole("button", { name: "Create a practice cycle" }).first(),
  );
  await click(page.getByLabel("What should learners be able to do next?"));
  await page
    .getByLabel("What should learners be able to do next?")
    .pressSequentially("Add fractions with unlike denominators.", {
      delay: 35,
    });
  await click(page.getByLabel("Closes at"));
  await page
    .getByLabel("Closes at")
    .fill(new Date(Date.now() + 2 * 86400000).toISOString().slice(0, 16));
  await click(page.getByLabel("Practice budget"));
  await page.getByLabel("Practice budget").fill("10");
  await hold(1000);
  await click(page.getByRole("button", { name: "Continue", exact: true }));
  await click(
    page.getByRole("button", { name: "Use objective and extract concepts" }),
  );
  await page
    .getByRole("heading", { name: "Check the concepts before planning" })
    .waitFor();
  await hold(1800);
  await click(
    page.getByRole("button", { name: "Confirm and prepare practice" }),
  );
  if (simulateAgent) {
    for (const [index, tool] of illustratedTools.entries()) {
      await expect(
        page.locator(`.agent-steps [data-tool="${tool}"]`),
      ).toHaveAttribute("data-status", "active", { timeout: 10000 });
      await expect(
        page.locator('.agent-steps [data-status="complete"]'),
      ).toHaveCount(index);
      await expect(page.locator(".draft-main")).toHaveCount(0);
    }
  }
  await page
    .getByRole("heading", { name: /Review 8 practice plans/ })
    .waitFor({ timeout: 120000 });
  if (simulateAgent)
    await expect(
      page.locator('.agent-steps [data-status="complete"]'),
    ).toHaveCount(4);
  await click(
    page.getByText(simulateAgent ? "Planning steps" : "See what ran", {
      exact: true,
    }),
  );
  await page.locator(".agent-trace ol").waitFor();
  await page.evaluate(() => window.scrollTo(0, 0));
  await hold(2000);
  const runResponse = await context.request.get(
    `/api/cycles/${cycleId}/agent-run`,
  );
  const run = await runResponse.json();
  await page.screenshot({ path: resolve("public/media/tiza-demo-poster.png") });
  await click(page.locator(".draft-main").first());
  await hold(2300);
  await click(page.getByRole("button", { name: "Approve this version" }));
  await hold(1000);
  await click(page.getByRole("button", { name: "Approve & send" }));
  await page.getByRole("heading", { name: "Current practice" }).waitFor();
  await hold(2200);
  await click(page.getByRole("button", { name: "Demo identity", exact: true }));
  await click(page.getByRole("button", { name: "Maya", exact: true }));
  await page.getByRole("button", { name: "Need a hint?" }).waitFor();
  await hold(1800);
  await click(page.getByRole("button", { name: "Need a hint?" }));
  await hold(1800);
  await click(page.locator(".options button").first());
  await click(page.getByRole("button", { name: "Save answer" }));
  await page
    .getByRole("status")
    .filter({ hasText: "Your answer was saved." })
    .waitFor();
  await hold(2000);
  for (let remaining = 12; remaining; remaining -= 1) {
    if (await page.getByText("Practice complete", { exact: true }).isVisible()) break;
    await click(page.getByRole("button", { name: "Continue", exact: true }));
    if (await page.getByText("Practice complete", { exact: true }).isVisible()) break;
    const options = page.locator(".options button");
    if (await options.count()) {
      await click(options.first());
    } else {
      const answer = page.getByLabel("Your answer", { exact: true });
      await click(answer);
      await answer.fill((await answer.getAttribute("placeholder")) === "Write a short explanation"
        ? "I used equal-sized parts to compare the fractions."
        : "0");
    }
    await click(page.getByRole("button", { name: "Save answer", exact: true }));
    await expect(page.getByRole("status")).toHaveText("Your answer was saved.");
    await hold(650);
  }
  await expect(page.getByText("Practice complete", { exact: true })).toBeVisible();
  await hold(1000);
  await click(page.getByRole("button", { name: "Return to teacher view" }));
  await click(page.getByRole("button", { name: "Next lesson", exact: true }));
  await page.getByRole("heading", { name: "Plan your next lesson" }).waitFor();
  await hold(3500);
  await writeFile(
    resolve("public/media/tiza-demo.json"),
    JSON.stringify(
      {
        recorded_at: new Date().toISOString(),
        synthetic: true,
        cursor_visible: true,
        cursor_style: "macos",
        agent_trace_illustrated: simulateAgent,
        illustrated_tools: simulateAgent ? illustratedTools : [],
        mode: run.mode,
        model_invoked: run.model_invoked,
        model: run.model,
        tools: run.tools,
        operations: run.operations,
        cycle_id: cycleId,
        note: simulateAgent
          ? "Real synthetic app flow with an illustrated agent tool sequence injected only in the recording browser. No model invocation or simulated trace is persisted."
          : "Actual browser session. Pauses pace the recording; no progress or model activity is simulated.",
      },
      null,
      2,
    ) + "\n",
  );
  await page.close();
  await writeFile(
    resolve("../../data/recordings/latest-path.txt"),
    await page.video().path(),
  );
} finally {
  await context.close();
  await browser.close();
}
