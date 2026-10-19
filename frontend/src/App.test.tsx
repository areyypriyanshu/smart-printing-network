import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";
import { createTestQueryClient } from "./test/render";

function renderApp() {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <App />
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
    expect(
      screen.getByRole("link", { name: /create an account/i }),
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
