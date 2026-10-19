import { CUSTOMER_EMAIL, CUSTOMER_PASSWORD } from "./helpers";

// One customer for the whole suite.
//
// The registration endpoint is rate limited per address, and every test
// in this suite comes from the same one. Registering a customer per
// test would trip that limit, so the customer is created once here and
// the journeys sign in with it.

export default async function globalSetup(): Promise<void> {
  const baseUrl = process.env.E2E_BASE_URL ?? "http://localhost:5173";
  const response = await fetch(`${baseUrl}/api/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: CUSTOMER_EMAIL,
      password: CUSTOMER_PASSWORD,
      full_name: "End To End Customer",
    }),
  });
  // 409 means the customer is already there from an earlier run, which
  // is exactly what we want.
  if (!response.ok && response.status !== 409) {
    throw new Error(
      `the test customer could not be created: ${response.status} ${await response.text()}`,
    );
  }
}
