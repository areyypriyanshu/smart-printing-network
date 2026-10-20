import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { ApiError } from "./api/client";
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

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
