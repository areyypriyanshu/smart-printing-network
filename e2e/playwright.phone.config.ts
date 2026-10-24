import { defineConfig } from "@playwright/test";

import base from "./playwright.config";

// The same offline journeys at a small phone viewport, with touch enabled.
// Run with: npm run test:phone -- tests/shop-search.spec.ts
export default defineConfig({
  ...base,
  use: {
    ...base.use,
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  },
});
