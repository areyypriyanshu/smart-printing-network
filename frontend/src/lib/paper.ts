/**
 * The paper sizes the platform prints on.
 *
 * The wizard and the rate card both work through the same list, so it is
 * written down once. If the two had their own copies, a new paper size
 * would appear on one screen and not the other.
 */
export const PAPER_SIZES = ["A4", "A3"] as const;

export type PaperSize = (typeof PAPER_SIZES)[number];
