/**
 * What a person said they were here for, before they had an account.
 *
 * The link that says "register your shop" carries the reason in the
 * address, and the sign up page puts it where the onboarding can find
 * it after the identity provider has sent the person back. Without it,
 * a shop owner is asked whether they want to print something or run a
 * shop, and they have already said.
 *
 * The reason is kept in the browser's own storage because the identity
 * provider's sign up happens in between: the person leaves for the
 * provider and comes back, and the reason has to survive the trip.
 */

const KEY = "spn:intent";

/** The person is here to run a shop. */
export const SHOP = "shop";

export type Intent = typeof SHOP | null;

/**
 * The reason in the address of a link, if it is one we know.
 *
 * A link that says `?as=shop` is a shop owner registering their shop.
 * Anything else is no reason at all, and the person is asked.
 */
export function intentFromQuery(value: string | null): Intent {
  return value === SHOP ? SHOP : null;
}

/** Keep the reason for the next page. */
export function rememberIntent(intent: Intent): void {
  try {
    if (intent === null) window.sessionStorage.removeItem(KEY);
    else window.sessionStorage.setItem(KEY, intent);
  } catch {
    // A browser that will not keep it still works. The person is
    // asked what they are here for, which is the old way.
  }
}

/** The reason that was kept, if there is one. */
export function readIntent(): Intent {
  try {
    return window.sessionStorage.getItem(KEY) === SHOP ? SHOP : null;
  } catch {
    return null;
  }
}

/** The reason has been used or abandoned. */
export function forgetIntent(): void {
  rememberIntent(null);
}
