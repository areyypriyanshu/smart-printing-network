import { ClerkProvider } from "@clerk/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { ApiError } from "./api/client";
import { ClerkSession, DevSession } from "./features/auth";
import "./index.css";

const container = document.getElementById("root");

if (!container) {
  throw new Error("root element missing");
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // A request the server answered with a 4xx will get the same
      // answer if it is sent again, so only a dropped connection or a
      // server fault is worth a second try. The wait between tries is
      // short, so a customer sees the error and a "Try again" button
      // instead of a spinner that goes on for eight seconds.
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status < 500) return false;
        return failureCount < 1;
      },
      retryDelay: 500,
    },
  },
});

/**
 * The publishable key, and the identity provider behind it.
 *
 * The key is public: it is in the browser's bundle either way, and it
 * can only be used to ask the provider who someone is, never to decide
 * anything. The secret key is the other one and it never comes near
 * the browser.
 */
const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY ?? "";

/**
 * Whether the end to end suite's local way in is used.
 *
 * The suite has to run offline, so it cannot sign in through the
 * provider. The setting is a build-time one, and the route behind it is
 * refused in production, so a deployment cannot have it.
 */
const DEV_AUTH = import.meta.env.VITE_SPN_DEV_AUTH === "true";

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      {DEV_AUTH ? (
        <DevSession>
          <App />
        </DevSession>
      ) : (
        <ClerkProvider publishableKey={PUBLISHABLE_KEY}>
          <ClerkSession>
            <App />
          </ClerkSession>
        </ClerkProvider>
      )}
    </QueryClientProvider>
  </StrictMode>,
);
