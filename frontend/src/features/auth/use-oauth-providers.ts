import { useQuery } from "@tanstack/react-query";

import { oauthProvidersRequest } from "./api";

/**
 * The providers this deployment offers.
 *
 * A deployment that has not configured Google does not show a button
 * that cannot work, so the front end asks the server what there is.
 */
export function useOAuthProviders(): string[] {
  const query = useQuery({
    queryKey: ["oauth-providers"],
    queryFn: oauthProvidersRequest,
    staleTime: 300000,
  });
  return query.data?.providers ?? [];
}
