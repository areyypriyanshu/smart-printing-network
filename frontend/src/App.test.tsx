import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";
import { createTestQueryClient, TestSession } from "./test/render";

function renderApp() {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <TestSession signedIn={false}>
        <App />
      </TestSession>
    </QueryClientProvider>,
  );
}

describe("App", () => {
  it("shows the landing page for anonymous visitors", async () => {
    renderApp();

    expect(
      await screen.findByRole("heading", {
        name: /print from a shop near you/i,
      }),
    ).toBeInTheDocument();
    // The call to action in the page, not the one in the header. Both
    // links are called "Create an account", so the page is picked by
    // where it is rather than by what it says.
    const main = screen.getByRole("main");
    expect(
      within(main).getByRole("link", { name: /create an account/i }),
    ).toBeInTheDocument();
  });

  it("shows a not-found page for unknown routes", async () => {
    window.history.pushState({}, "", "/does-not-exist");
    renderApp();

    expect(
      await screen.findByRole("heading", { name: /page not found/i }),
    ).toBeInTheDocument();
    window.history.pushState({}, "", "/");
  });
});
