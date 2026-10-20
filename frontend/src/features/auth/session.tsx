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
  refreshAccessToken,
  setAccessToken,
  setSessionExpiredHandler,
  type User,
} from "../../api/client";
import { loginRequest, logoutRequest, meRequest } from "./api";

type SessionState =
  | { status: "loading"; user: null }
  | { status: "anonymous"; user: null }
  | { status: "authenticated"; user: User };

type SessionContextValue = {
  status: SessionState["status"];
  user: User | null;
  login: (email: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  /** Read the account again, for when something about it has changed. */
  refreshUser: () => Promise<User>;
};

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SessionState>({
    status: "loading",
    user: null,
  });

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const token = await refreshAccessToken();
      if (cancelled) return;
      if (token === null) {
        setState({ status: "anonymous", user: null });
        return;
      }
      try {
        const user = await meRequest();
        if (!cancelled) setState({ status: "authenticated", user });
      } catch {
        if (!cancelled) setState({ status: "anonymous", user: null });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setSessionExpiredHandler(() =>
      setState({ status: "anonymous", user: null }),
    );
    return () => setSessionExpiredHandler(null);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await loginRequest({ email, password });
    setAccessToken(tokens.access_token);
    try {
      const user = await meRequest();
      setState({ status: "authenticated", user });
      return user;
    } catch (error) {
      setAccessToken(null);
      setState({ status: "anonymous", user: null });
      throw error;
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await logoutRequest();
    } catch {
      // The refresh cookie may already be gone; the local session still ends.
    }
    setAccessToken(null);
    setState({ status: "anonymous", user: null });
  }, []);

  const refreshUser = useCallback(async () => {
    const user = await meRequest();
    setState({ status: "authenticated", user });
    return user;
  }, []);

  const value = useMemo(
    () => ({
      status: state.status,
      user: state.user,
      login,
      logout,
      refreshUser,
    }),
    [state.status, state.user, login, logout, refreshUser],
  );

  return (
    <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
  );
}

export function useSession(): SessionContextValue {
  const value = useContext(SessionContext);
  if (value === null) {
    throw new Error("useSession must be used inside SessionProvider");
  }
  return value;
}
