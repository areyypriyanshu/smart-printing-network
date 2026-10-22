import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// The pages a customer can reach without an account. The rules are the
// WCAG 2.1 A and AA levels, which is the target in the PRD.
//
// The shop registration page is not among them: it was a page of its
// own, and it is part of the account now, where a person says they run
// a shop. It needs a session to reach, so it is not a public page.
const PUBLIC_PAGES = [
  { name: "the landing page", path: "/" },
  { name: "the sign in page", path: "/login" },
  { name: "the registration page", path: "/register" },
];

for (const target of PUBLIC_PAGES) {
  test(`${target.name} has no automatically detectable accessibility violations`, async ({
    page,
  }) => {
    await page.goto(target.path);

    // The page has to be the one that was asked for. A path that no
    // route serves answers with the page that says so, and that page
    // has no accessibility problems, so the check would pass while
    // saying nothing about the page it names.
    await expect(
      page.getByRole("heading", { name: "Page not found" }),
    ).toHaveCount(0);

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();

    expect(
      results.violations.map((violation) => ({
        id: violation.id,
        impact: violation.impact,
        help: violation.help,
        nodes: violation.nodes.map((node) => node.target),
      })),
    ).toEqual([]);
  });
}
