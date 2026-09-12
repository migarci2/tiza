import { expect, test } from "@playwright/test";

test("completes a reviewed practice cycle and updates the lesson brief", async ({
  page,
}) => {
  test.setTimeout(90_000);
  await page.goto("/");
  await expect(page.getByLabel("Email", { exact: true })).toHaveCount(0);
  await page.getByLabel("Demo code", { exact: true }).fill("246810");
  await page.getByRole("button", { name: "Enter workspace" }).click();
  await expect(
    page.getByRole("heading", { name: /Practice between classes/ }),
  ).toBeVisible();

  await page
    .getByRole("button", { name: "Demo identity", exact: true })
    .click();
  const resetResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/demo/reset" &&
      response.ok(),
  );
  await page.getByRole("button", { name: "Reset demo" }).click();
  await resetResponse;
  await page.keyboard.press("Escape");
  await expect(page.getByRole("status")).toContainText("Demo data restored");

  await page
    .getByRole("button", { name: "Create a practice cycle" })
    .first()
    .click();
  await page
    .getByLabel("What should learners be able to do next?")
    .fill("Add fractions with unlike denominators using equivalent fractions.");
  const closesAt = new Date(Date.now() + 2 * 86_400_000)
    .toISOString()
    .slice(0, 16);
  await page.getByLabel("Closes at").fill(closesAt);
  await page.getByLabel("Practice budget").fill("10");
  await page.getByRole("button", { name: "Continue" }).click();
  await page
    .getByRole("button", { name: "Use objective and extract concepts" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Check the concepts before planning" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Confirm and prepare practice" })
    .click();

  const reviewHeading = page.getByRole("heading", {
    name: /Review 8 practice plans/,
  });
  const reviewPractice = page.getByRole("button", { name: "Review practice" });
  await expect(reviewHeading.or(reviewPractice)).toBeVisible({
    timeout: 30_000,
  });
  if (await reviewPractice.isVisible()) await reviewPractice.click();
  await expect(reviewHeading).toBeVisible();
  await expect(page.getByRole("heading", { name: "Practice agent", exact: true })).toBeVisible();
  await expect(page.getByText("Version 1")).toBeVisible();
  await page.getByText("See what ran", { exact: true }).click();
  await expect(page.locator(".agent-mode")).toContainText(
    "No AI model was invoked",
  );
  await expect(page.locator(".agent-activity")).toContainText(
    "8 practice plans",
  );
  const mayaDraft = page.locator(".draft-main").filter({ hasText: "Maya" });
  await mayaDraft.click();
  await expect(page.locator(".exercise-preview").first()).toBeVisible();
  const parentExercise = page.locator(".exercise-preview select").first();
  await expect(
    parentExercise.locator('option[value="frac-parts-check-v1"]'),
  ).toHaveCount(1);
  const parentUpdate = page.waitForResponse(
    (response) =>
      response.request().method() === "PATCH" &&
      /\/api\/cycles\/[^/]+\/draft$/.test(new URL(response.url()).pathname) &&
      response.ok(),
  );
  await parentExercise.selectOption("frac-parts-check-v1");
  await parentUpdate;
  await mayaDraft.click();
  await expect(page.locator(".exercise-preview").first()).toBeVisible();
  const branchExercise = page.locator(".exercise-preview select").nth(1);
  const shortResponse = branchExercise
    .locator("option")
    .filter({ hasText: "Explain" });
  await expect(shortResponse).toHaveCount(1);
  const shortResponseId = await shortResponse.getAttribute("value");
  expect(shortResponseId).not.toBeNull();
  const draftUpdate = page.waitForResponse(
    (response) =>
      response.request().method() === "PATCH" &&
      /\/api\/cycles\/[^/]+\/draft$/.test(new URL(response.url()).pathname) &&
      response.ok(),
  );
  await branchExercise.selectOption(shortResponseId!);
  await draftUpdate;
  await page.getByRole("button", { name: "Approve this version" }).click();
  await page.getByRole("button", { name: "Approve & send" }).click();
  await expect(
    page.getByRole("heading", { name: "Current practice" }),
  ).toBeVisible();
  await expect(page.getByText("8 queued")).toBeVisible();

  const assignmentResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      response.ok() &&
      /\/api\/assignments\/[^/]+$/.test(new URL(response.url()).pathname),
  );
  await page
    .getByRole("button", { name: "Demo identity", exact: true })
    .click();
  await page.getByRole("button", { name: "Maya", exact: true }).click();
  const assignment = (await (await assignmentResponse).json()) as {
    id: string;
    state: string;
    items: Array<{ attempt?: unknown; exercise: Record<string, unknown> }>;
  };
  expect(
    assignment.items.every(
      ({ exercise }) => !("answer" in exercise) && !("explanation" in exercise),
    ),
  ).toBe(true);

  await expect(
    page.getByRole("heading", {
      name: "Add fractions with unlike denominators using equivalent fractions.",
    }),
  ).toBeVisible();
  const initialQuestion = await page.locator(".question").textContent();
  await page.getByRole("button", { name: "Need a hint?" }).click();
  await expect(page.locator(".hint")).toBeVisible();
  await page.locator(".options button").first().click();
  const attemptResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      /\/api\/assignments\/[^/]+\/attempts$/.test(
        new URL(response.url()).pathname,
      ) &&
      response.ok(),
  );
  await page.getByRole("button", { name: "Save answer" }).click();
  expect((await (await attemptResponse).json()).result).toBe("incorrect");
  await expect(page.getByRole("status")).toHaveText("Your answer was saved.");
  await expect(page.locator(".question")).toHaveText(initialQuestion ?? "");
  await expect(page.getByText("Keep practising.")).toBeVisible();

  await page.getByRole("button", { name: "Continue" }).click();
  await expect(
    page.getByPlaceholder("Write a short explanation"),
  ).toBeVisible();
  await page
    .getByPlaceholder("Write a short explanation")
    .fill("The denominators name different-sized parts.");
  const shortQuestion = await page.locator(".question").textContent();
  const reviewResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      /\/api\/assignments\/[^/]+\/attempts$/.test(
        new URL(response.url()).pathname,
      ) &&
      response.ok(),
  );
  await page.getByRole("button", { name: "Save answer" }).click();
  expect((await (await reviewResponse).json()).result).toBe("review_needed");
  await expect(page.getByText("Your teacher will review this.")).toBeVisible();
  await expect(page.locator(".question")).toHaveText(shortQuestion ?? "");

  for (let remaining = 10; remaining; remaining -= 1) {
    if (await page.getByText("Practice complete").isVisible()) break;
    await page.getByRole("button", { name: "Continue" }).click();
    if (await page.getByText("Practice complete").isVisible()) break;

    const options = page.locator(".options button");
    if (await options.count()) await options.first().click();
    else await page.locator(".answer-field input").fill("0");

    const response = page.waitForResponse(
      (value) =>
        value.request().method() === "POST" &&
        /\/api\/assignments\/[^/]+\/attempts$/.test(
          new URL(value.url()).pathname,
        ) &&
        value.ok(),
    );
    await page.getByRole("button", { name: "Save answer" }).click();
    await response;
    await expect(page.getByRole("status")).toHaveText("Your answer was saved.");
  }
  await expect(
    page.getByRole("heading", { name: "Your teacher will review your explanations." }),
  ).toBeVisible();
  const completedAssignment = (await (
    await page.request.get(`/api/assignments/${assignment.id}`)
  ).json()) as {
    state: string;
    items: Array<{ attempt?: unknown }>;
  };
  expect(completedAssignment.state).toBe("review_needed");
  expect(completedAssignment.items.every((item) => item.attempt)).toBe(true);

  await page.getByRole("button", { name: "Return to teacher view" }).click();
  await expect(page.getByRole("button", { name: "Next lesson" })).toBeVisible();
  await page.getByRole("button", { name: "Next lesson" }).click();
  await expect(
    page.getByRole("heading", { name: "Plan your next lesson" }),
  ).toBeVisible();
  await expect(
    page.getByText(/1 submitted response.*reinforcement/),
  ).toBeVisible();
  await expect(page.getByText("1 supporting attempt")).toBeVisible();
  await page.getByText("View supporting attempts").click();
  await expect(page.getByText("Maya", { exact: true })).toBeVisible();
  await expect(page.locator("blockquote").first()).toHaveText("a");
  await expect(page.getByText(/incorrect · A hint was used/)).toBeVisible();
  await expect(page.getByText("1need review")).toBeVisible();
  await expect(page.getByText("The denominators name different-sized parts.")).toBeVisible();
  const markCorrect = page.getByRole("button", { name: "Mark correct" });
  await expect(markCorrect.first()).toBeVisible();
  for (let pending = 4; pending && (await markCorrect.count()); pending -= 1) {
    const count = await markCorrect.count();
    const review = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        /\/api\/attempts\/[^/]+\/review$/.test(new URL(response.url()).pathname) &&
        response.ok(),
    );
    await markCorrect.first().click();
    await review;
    await expect.poll(() => markCorrect.count()).toBeLessThan(count);
  }
  await expect(
    page.getByText("No explanations are waiting for review."),
  ).toBeVisible();
  await expect(page.locator(".big-number")).toContainText("1of 8 completed");

  await page
    .getByRole("button", { name: "Demo identity", exact: true })
    .click();
  await Promise.all([
    page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === "/api/demo/reset" &&
        response.ok(),
    ),
    page.getByRole("button", { name: "Reset demo" }).click(),
  ]);
});
