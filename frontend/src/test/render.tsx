import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter } from "react-router";

import { SessionProvider } from "../features/auth";

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

export function TestProviders({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={createTestQueryClient()}>
      <SessionProvider>
        <MemoryRouter>{children}</MemoryRouter>
      </SessionProvider>
    </QueryClientProvider>
  );
}

export function renderWithProviders(
  ui: ReactElement,
  { route = "/", state }: { route?: string; state?: unknown } = {},
) {
  // The route is split into its path and its query, because a location
  // given as an object keeps the query in the search and not in the
  // path, and a screen that reads a query parameter needs it there.
  const [pathname, search] = route.split("?");
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <SessionProvider>
        <MemoryRouter
          initialEntries={[
            {
              pathname,
              search: search === undefined ? "" : `?${search}`,
              state,
            },
          ]}
        >
          {ui}
        </MemoryRouter>
      </SessionProvider>
    </QueryClientProvider>,
  );
}
