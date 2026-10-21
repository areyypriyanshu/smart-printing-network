import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  ApiError,
  apiRequest,
  setTokenSource,
  type User,
} from "../../api/client";

/**
 * What the application knows about the person using it.
 *
 * There are four states, and they are four because the interesting
 * middle one is real: a person can have signed in and still have no
 * account, because they have not yet said whether they are here to
 * print something or to run a shop. That is a different thing from
 * being signed out, and it needs a different page.
 */
export type SessionState =
  | { status: "loading"; user: null }
  | { status: "anonymous"; user: null }
  | { status: "needs-onboarding"; user: null }
  | { status: "authenticated"; user: User };

export type SessionContextValue = {
  status: SessionState["status"];
  user: User | null;
  logout: () => Promise<void>;
  /** Read the account again, for when something about it has changed. */
  refreshUser: () => Promise<User>;
};

const SessionContext = createContext<SessionContextValue | null>(null);

export function useSession(): SessionContextValue {
  const value = useContext(SessionContext);
  if (value === null) {
    throw new Error("useSession must be used inside a session provider");
  }
  return value;
}

/**
 * The session, for whoever is holding the token.
 *
 * The token itself is the identity provider's business. This asks for
 * one when a request needs it, asks the application who the token
 * names, and keeps the answer. The provider is the only thing that
 * differs between the two ways this is used: the real one and the
 * local stand-in the end to end suite uses.
 */
export function SessionProvider({
  children,
  getToken,
  signOut,
  signedIn,
  loaded,
}: {
  children: ReactNode;
  /** A fresh token, or nothing when there is no session. */
  getToken: () => Promise<string | null>;
  /** End the session wherever it is held. */
  signOut: () => Promise<void>;
  /** Whether there is a session at all. */
  signedIn: boolean;
  /**
   * Whether the provider has finished finding out.
   *
   * It matters, because "not signed in" and "not looked yet" are two
   * different answers and the application has to wait for the second
   * one before it believes the first. A person who has just signed in
   * is signed in before the provider has finished loading, and a
   * session that decided otherwise would send them back to the sign in
   * page they had just left.
   */
  loaded: boolean;
}) {
  const [state, setState] = useState<SessionState>({
    status: "loading",
    user: null,
  });

  // The API client asks for the token when it needs one, so the token
  // is never held here and never goes stale.
  useEffect(() => {
    setTokenSource(getToken);
    return () => setTokenSource(null);
  }, [getToken]);

  // The answer is returned rather than written straight into the state,
  // because the answer arrives after an await and the component may be
  // gone by then. Writing it from here would be a change to a
  // component that is no longer on the page.
  const read = useCallback(async (): Promise<SessionState | null> => {
    if (!loaded) {
      // The provider has not finished looking yet. Nothing is decided
      // until it has.
      return null;
    }
    if (!signedIn) {
      return { status: "anonymous", user: null };
    }
    const token = await getToken();
    if (token === null) {
      return { status: "anonymous", user: null };
    }
    try {
      const user = await apiRequest<User>("/me");
      return { status: "authenticated", user };
    } catch (error) {
      if (
        error instanceof ApiError &&
        error.status === 403 &&
        error.code === "ACCOUNT_NOT_PROVISIONED"
      ) {
        // The token is good and the person has not chosen yet.
        return { status: "needs-onboarding", user: null };
      }
      return { status: "anonymous", user: null };
    }
  }, [getToken, loaded, signedIn]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const next = await read();
      if (cancelled || next === null) return;
      setState(next);
    })();
    return () => {
      cancelled = true;
    };
  }, [read]);

  const logout = useCallback(async () => {
    try {
      await signOut();
    } catch {
      // The session may already be gone; the local one still ends.
    }
    setState({ status: "anonymous", user: null });
  }, [signOut]);

  const refreshUser = useCallback(async () => {
    const user = await apiRequest<User>("/me");
    setState({ status: "authenticated", user });
    return user;
  }, []);

  const value = useMemo(
    () => ({
      status: state.status,
      user: state.user,
      logout,
      refreshUser,
    }),
    [state.status, state.user, logout, refreshUser],
  );

  return (
    <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
  );
}
