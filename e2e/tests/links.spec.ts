import { expect, test } from "@playwright/test";

// Every link in the application has to lead to a page that exists.
//
// A link to a page that is not there is the quietest kind of mistake:
// the person who follows it is told "page not found" and has no way of
// knowing that the link was the problem and not the page. The route
// that served a shop registration was removed when the identity
// provider took the sign in, and two links kept pointing at it.
//
// The check is a walk: every link on the landing page is followed, and
// the page it leads to has to be a page the application serves.

test("no link leads to a page that does not exist", async ({ page }) => {
  await page.goto("/");

  const hrefs = await page
    .locator("a[href^='/']")
    .evaluateAll((links) =>
      links.map(
        (link) => (link as HTMLAnchorElement).getAttribute("href") ?? "",
      ),
    );

  expect(hrefs.length).toBeGreaterThan(0);

  for (const href of hrefs) {
    await page.goto(href);
    await expect(
      page.getByRole("heading", { name: "Page not found" }),
    ).toHaveCount(0);
  }
});

test("the call to register a shop leads to the sign up", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("link", { name: "Register your shop" }).click();

  await expect(page).toHaveURL(/\/register/);
  await expect(
    page.getByRole("heading", { name: "Page not found" }),
  ).toHaveCount(0);
});
