import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { forgetIntent } from "../features/auth/intent";
import { server } from "./msw/server";

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
  // The reason a person gave is kept in the browser's own storage, and
  // the storage outlives a test.
  forgetIntent();
});
afterAll(() => server.close());
