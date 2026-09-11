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
  await page.locator(".draft-main").first().click();
  await expect(page.locator(".exercise-preview").first()).toBeVisible();
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
    items: Array<{ exercise: Record<string, unknown> }>;
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
  await expect(page.getByText("Keep practising.")).toBeVisible();

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
  await expect(page.locator("blockquote")).toHaveText("a");
  await expect(page.getByText(/incorrect · A hint was used/)).toBeVisible();

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
