import {
  apiRequest,
  type OnboardingRequest,
  type User,
} from "../../api/client";

/** The account the caller is. */
export function meRequest(): Promise<User> {
  return apiRequest("/me");
}

/**
 * Make the account, once the person has said what they are here for.
 *
 * The body carries the intent and nothing else. The address and the
 * name are read by the server from the identity provider, because the
 * provider proved them and the browser did not.
 */
export function onboardRequest(body: OnboardingRequest): Promise<User> {
  return apiRequest("/auth/onboarding", { method: "POST", body });
}
