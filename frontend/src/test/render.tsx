import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { useCallback, useState, type ReactElement, type ReactNode } from "react";
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

/**
 * A session for the tests.
 *
 * The token is a fixed string, because the server in the tests is a
 * mock and the token is only there to be sent. Whether there is a
 * session at all is decided by the `signedIn` prop, so a test can
 * exercise the signed-out screens and the signed-in ones.
 */
export function TestSession({
  children,
  signedIn = true,
}: {
  children: ReactNode;
  signedIn?: boolean;
}) {
  const getToken = useCallback(async () => (signedIn ? "test-token" : null), [signedIn]);
  const signOut = useCallback(async () => {}, []);
  return (
    <SessionProvider
      getToken={getToken}
      signOut={signOut}
      signedIn={signedIn}
      loaded
    >
      {children}
    </SessionProvider>
  );
}

export function TestProviders({
  children,
  signedIn = true,
}: {
  children: ReactNode;
  signedIn?: boolean;
}) {
  return (
    <QueryClientProvider client={createTestQueryClient()}>
      <TestSession signedIn={signedIn}>
        <MemoryRouter>{children}</MemoryRouter>
      </TestSession>
    </QueryClientProvider>
  );
}

export function renderWithProviders(
  ui: ReactElement,
  {
    route = "/",
    state,
    signedIn = true,
  }: { route?: string; state?: unknown; signedIn?: boolean } = {},
) {
  // The route is split into its path and its query, because a location
  // given as an object keeps the query in the search and not in the
  // path, and a screen that reads a query parameter needs it there.
  const [pathname, search] = route.split("?");
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <TestSession signedIn={signedIn}>
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
      </TestSession>
    </QueryClientProvider>,
  );
}

/** A re-render helper for the screens that change with the session. */
export function useTestSessionState() {
  const [signedIn, setSignedIn] = useState(true);
  return { signedIn, setSignedIn };
}
