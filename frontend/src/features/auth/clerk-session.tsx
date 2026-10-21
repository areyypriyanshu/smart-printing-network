import { useAuth } from "@clerk/react";
import { useCallback, type ReactNode } from "react";

import { SessionProvider } from "./session";

/**
 * The session, when the identity provider holds it.
 *
 * The provider is the one that knows about the token, and the
 * application only ever asks for a fresh one. The token lives for
 * about a minute, so a token held in the application would be one that
 * has expired.
 */
export function ClerkSession({ children }: { children: ReactNode }) {
  const { isLoaded, isSignedIn, getToken, signOut } = useAuth();

  const fetchToken = useCallback(() => getToken(), [getToken]);

  return (
    <SessionProvider
      getToken={fetchToken}
      signOut={signOut}
      signedIn={isSignedIn === true}
      loaded={isLoaded}
    >
      {children}
    </SessionProvider>
  );
}
