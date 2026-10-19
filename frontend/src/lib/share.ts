/**
 * Sharing the pickup code.
 *
 * The code is the only thing the shop checks at the counter, so whoever
 * has it can collect the printout. A lot of pickups are not the person
 * who ordered: a roommate collects, a friend picks up for a lab
 * partner. Sending the code over WhatsApp is the simplest way to hand
 * it over, and it costs nothing to build.
 *
 * The link is a plain wa.me link with the message in it. There is no
 * business API, no account and no cost.
 */

const WHATSAPP_URL = "https://wa.me/";

export type PickupShare = {
  order_no: number;
  pickup_code: string;
  shopName?: string | null;
};

export function whatsappLink(message: string): string {
  return `${WHATSAPP_URL}?text=${encodeURIComponent(message)}`;
}

/**
 * The message to send. It says which order it is, which shop it is
 * from, and the code.
 */
export function pickupMessage(order: PickupShare): string {
  const shop = order.shopName ? ` from ${order.shopName}` : "";
  return (
    `Hi, I am collecting a print order${shop}. ` +
    `My pickup code is ${order.pickup_code} (order #${order.order_no}).`
  );
}

export function pickupShareLink(order: PickupShare): string {
  return whatsappLink(pickupMessage(order));
}
