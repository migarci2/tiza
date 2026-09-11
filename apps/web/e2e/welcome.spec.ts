import { expect, test } from "@playwright/test";

test("landing offers code access and adapts to mobile", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Class ends. Practice begins." }),
  ).toBeVisible();
  const landingFont = await page
    .locator(".tiza-landing")
    .evaluate((element) => getComputedStyle(element).fontFamily);
  const landingPrimary = await page
    .locator(".story-button")
    .first()
    .evaluate((element) => getComputedStyle(element).backgroundColor);
  await expect(
    page.getByRole("button", { name: "Open demo workspace" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Pause product demo" }),
  ).toBeVisible();
  await page.locator(".demo-film").hover();
  await page.getByRole("button", { name: "Pause product demo" }).click();
  await expect(page.locator("video")).toHaveJSProperty("paused", true);
  await page.locator("video").evaluate((video: HTMLVideoElement) => {
    video.currentTime = 0;
  });
  await expect(page.getByRole("link", { name: "Download GIF" })).toHaveCount(0);
  await expect(
    page.locator(".demo-film-top, .demo-film-controls, .demo-hackathon"),
  ).toHaveCount(0);
  await expect(page.locator(".demo-film figcaption")).toContainText(
    "Illustrated agent sequence",
  );
  await page.screenshot({ path: "../../docs/design/story-hero-desktop.png" });
  await page
    .getByRole("navigation", { name: "The Tiza cycle" })
    .getByRole("link", { name: /The practice/ })
    .click();
  await expect(page.locator(".story-stage")).toHaveAttribute(
    "data-active-chapter",
    "1",
  );
  await expect(
    page
      .getByRole("navigation", { name: "The Tiza cycle" })
      .getByRole("link", { name: /The practice/ }),
  ).toHaveAttribute("aria-current", "step");
  await expect(page.locator(".story-scene").nth(1)).toHaveCSS("opacity", "1");
  await expect(page.locator(".story-scene").first()).toHaveCSS("opacity", "0");
  await page.screenshot({
    path: "../../docs/design/story-practice-desktop.png",
  });
  await page.locator("#story-return").scrollIntoViewIfNeeded();
  await expect(page.locator(".story-stage")).toHaveAttribute(
    "data-active-chapter",
    "2",
  );
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(
    390,
  );
  await page.screenshot({ path: "../../docs/design/story-hero-mobile.png" });
  await page
    .getByRole("navigation", { name: "The Tiza cycle" })
    .getByRole("link", { name: /The practice/ })
    .click();
  await expect(page.locator(".story-stage")).toHaveAttribute(
    "data-active-chapter",
    "1",
  );
  await expect(page.locator(".story-scene").nth(1)).toHaveCSS("opacity", "1");
  await expect(page.locator(".story-scene").nth(2)).toHaveCSS("opacity", "0");
  await page.screenshot({
    path: "../../docs/design/story-practice-mobile.png",
  });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.locator("video")).toHaveJSProperty("paused", true);
  await expect(page.locator(".story-scene").first()).toHaveCSS(
    "transition-duration",
    "0s",
  );
  await expect(page.getByLabel("Email", { exact: true })).toHaveCount(0);
  await page.getByLabel("Demo code", { exact: true }).fill("000000");
  await page.getByRole("button", { name: "Enter workspace" }).click();
  await expect(page.getByRole("alert")).toContainText("Invalid demo code");
  await page.getByLabel("Demo code", { exact: true }).fill("246810");
  await page.getByRole("button", { name: "Enter workspace" }).click();
  await expect(page).toHaveURL(/\/workspace$/);
  await expect(
    page.getByRole("heading", { name: /Practice between classes/ }),
  ).toBeVisible();
  await expect(page.locator(".workspace")).toHaveCSS(
    "font-family",
    landingFont,
  );
  await expect(page.locator(".button.primary").first()).toHaveCSS(
    "background-color",
    landingPrimary,
  );
  await expect(page.locator(".wordmark .story-brand-mark")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(
    390,
  );
  await page.screenshot({ path: "../../docs/design/tiza-mobile.png" });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({ path: "../../docs/design/tiza-desktop.png" });
});
