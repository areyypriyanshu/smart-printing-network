/**
 * The browser leaves the application.
 *
 * The address is on another site, so a router cannot take the browser
 * there: the whole page is replaced. It is a module of its own so that
 * a test can stand in for it.
 */
export function openExternal(url: string): void {
  window.location.assign(url);
}
