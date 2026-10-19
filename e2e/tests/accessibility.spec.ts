import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// The pages a customer can reach without an account. The rules are the
// WCAG 2.1 A and AA levels, which is the target in the PRD.
const PUBLIC_PAGES = [
  { name: "the landing page", path: "/" },
  { name: "the sign in page", path: "/login" },
  { name: "the registration page", path: "/register" },
  { name: "the shop registration page", path: "/register-vendor" },
];

for (const target of PUBLIC_PAGES) {
  test(`${target.name} has no automatically detectable accessibility violations`, async ({
    page,
  }) => {
    await page.goto(target.path);

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
