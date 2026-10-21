import { CUSTOMER_EMAIL } from "./helpers";

// One customer for the whole suite.
//
// The suite signs in through the local way in, which the application
// offers when the identity provider is not in the picture. The route
// behind it is refused in production, so the suite cannot be run
// against a deployment that matters.
//
// The account is made here rather than in each test, so that the
// journeys do not each make one.

export default async function globalSetup(): Promise<void> {
  const baseUrl = process.env.E2E_BASE_URL ?? "http://localhost:5173";
  const response = await fetch(`${baseUrl}/api/v1/auth/dev-session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: CUSTOMER_EMAIL,
      full_name: "End To End Customer",
    }),
  });
  if (!response.ok) {
    throw new Error(
      `the test customer could not be created: ${response.status} ${await response.text()}`,
    );
  }
}
