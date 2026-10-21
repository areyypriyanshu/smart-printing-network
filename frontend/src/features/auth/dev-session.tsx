import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { apiRequest } from "../../api/client";
import { SessionProvider } from "./session";

/**
 * The session, when the end to end suite holds it.
 *
 * The suite has to run offline and the same way every time, so it
 * cannot sign in through the identity provider. The application still
 * reads the session the same way it always did: it asks for a token
 * and asks the server who the token names. The only thing that is
 * different is who signed the token, and the route that does it is
 * refused in production.
 */

const TOKEN_KEY = "spn.dev.token";

type DevAuthContextValue = {
  /** Sign in as the account with this address, creating it if it is not there. */
  signIn: (email: string) => Promise<void>;
};

const DevAuthContext = createContext<DevAuthContextValue | null>(null);

export function useDevAuth(): DevAuthContextValue {
  const value = useContext(DevAuthContext);
  if (value === null) {
    throw new Error("useDevAuth must be used inside the local session");
  }
  return value;
}

export function DevSession({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() =>
    window.localStorage.getItem(TOKEN_KEY),
  );

  const getToken = useCallback(async () => token, [token]);

  const signOut = useCallback(async () => {
    window.localStorage.removeItem(TOKEN_KEY);
    setToken(null);
  }, []);

  const signIn = useCallback(async (email: string) => {
    const response = await apiRequest<{ access_token: string }>(
      "/auth/dev-session",
      { method: "POST", body: { email } },
    );
    window.localStorage.setItem(TOKEN_KEY, response.access_token);
    setToken(response.access_token);
  }, []);

  const value = useMemo(() => ({ signIn }), [signIn]);

  return (
    <DevAuthContext.Provider value={value}>
      <SessionProvider
        getToken={getToken}
        signOut={signOut}
        signedIn={token !== null}
        loaded
      >
        {children}
      </SessionProvider>
    </DevAuthContext.Provider>
  );
}
