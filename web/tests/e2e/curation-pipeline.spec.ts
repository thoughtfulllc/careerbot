import { test, expect } from "@playwright/test";
import matter from "gray-matter";
import {
  fileExists,
  readFile,
  setupMidPipeline,
  setupWithCompanies,
} from "../setup/fixtures";

test.describe("Curation + applications pipeline", () => {
  test("company status: In Review → Interested moves the file", async ({ page }) => {
    await setupWithCompanies({ inReview: ["stripe"] });
    await page.goto("/companies");

    // Find Stripe's row and its status pill (the StatusSelect trigger).
    const stripeRow = page.getByRole("link", { name: /Stripe/ });
    await expect(stripeRow).toBeVisible();
    await stripeRow.locator("button", { hasText: /In Review/ }).click();
    await page.getByRole("option", { name: /^Interested$/ }).click();

    // Wait for the toast confirming success.
    await expect(page.getByText(/Status changed to Interested/)).toBeVisible();

    // Disk: file moved.
    expect(await fileExists("companies/interested/stripe.md")).toBe(true);
    expect(await fileExists("companies/in-review/stripe.md")).toBe(false);
  });

  test("applications page lists all three fixture rows", async ({ page }) => {
    await setupMidPipeline();
    await page.goto("/applications");
    await expect(page.getByText("Senior Product Designer", { exact: true })).toBeVisible();
    await expect(page.getByText("Staff Product Designer", { exact: true })).toBeVisible();
    await expect(page.getByText("Senior Product Manager", { exact: true })).toBeVisible();
  });

  test("application detail page renders synthesized answer", async ({ page }) => {
    await setupMidPipeline();
    await page.goto("/applications/in-review__linear__full-synth-engineer");
    await page.getByRole("tab", { name: "Answers" }).click();
    await expect(
      page.getByText(/Linear sets the bar for product polish/i),
    ).toBeVisible();
    await expect(page.getByText(/\[synthesized from:/).first()).toBeVisible();
  });

  test("application detail page renders partial-synth marker", async ({ page }) => {
    await setupMidPipeline();
    await page.goto("/applications/in-review__linear__partial-synth-designer");
    await page.getByRole("tab", { name: "Answers" }).click();
    await expect(page.getByText(/\[partial — pending:/)).toBeVisible();
  });

  test("application detail page renders all-TODO block", async ({ page }) => {
    await setupMidPipeline();
    await page.goto("/applications/in-review__linear__all-todo-pm");
    await page.getByRole("tab", { name: "Answers" }).click();
    await expect(
      page.getByText(/TODO: needs answers for the following/).first(),
    ).toBeVisible();
  });

  test("application status: In Review → Applied moves the file", async ({ page }) => {
    await setupMidPipeline();
    await page.goto("/applications");

    const row = page.getByRole("link", { name: /Senior Product Designer/ });
    await expect(row).toBeVisible();
    // Hover the row to reveal the next-step action buttons, then click "Applied".
    await row.hover();
    await row.getByRole("button", { name: /^Applied$/ }).click();

    await expect(page.getByText(/Status changed to Applied/)).toBeVisible();

    // updateApplication preserves the filename, only moves to a new status folder.
    expect(
      await fileExists("applications/applied/linear/full-synth-engineer.md"),
    ).toBe(true);
    expect(
      await fileExists("applications/in-review/linear/full-synth-engineer.md"),
    ).toBe(false);
  });

  test("answer-bank stub: fill body persists to disk", async ({ page }) => {
    await setupMidPipeline();
    // Beliefs/culture-fit starts as a stub (empty body).
    await page.goto("/answer-bank/beliefs__culture-fit");

    const textarea = page.getByRole("textbox", { name: /Canonical Answer/i });
    await textarea.fill("Energizing: small teams that ship weekly. Draining: status meetings.");
    await page.getByRole("button", { name: /Save changes/i }).click();
    await expect(page.getByText(/Saved|Save/)).toBeVisible({ timeout: 5_000 });

    // Disk: body now non-empty.
    const raw = await readFile("answer-bank/beliefs/culture-fit.md");
    const parsed = matter(raw);
    expect(parsed.content.trim()).not.toBe("");
    expect(parsed.content).toMatch(/Energizing|Draining/);

    // Partial-synth essay still references this stub path (the linkage is preserved;
    // actual re-synthesis is /draft-missing-answers' job, out of scope here).
    const essay = await readFile("applications/in-review/linear/partial-synth-designer.md");
    expect(essay).toMatch(/answer-bank\/career\/companies-admired\.md/);
  });
});
