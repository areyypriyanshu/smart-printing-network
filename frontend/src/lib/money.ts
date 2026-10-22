const inr = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
});

export const formatPaise = (paise: number): string => inr.format(paise / 100);

const RUPEES_PATTERN = /^\d+(\.\d{1,2})?$/;

export const isValidRupeesInput = (input: string): boolean =>
  RUPEES_PATTERN.test(input.trim()) && Number(input) > 0;

export const parseRupeesToPaise = (input: string): number | null => {
  const trimmed = input.trim();
  if (!isValidRupeesInput(trimmed)) return null;
  return Math.round(Number(trimmed) * 100);
};

export const formatPaiseForInput = (paise: number): string => {
  if (paise === 0) return "";
  const rupees = paise / 100;
  return Number.isInteger(rupees)
    ? String(rupees)
    : rupees.toFixed(2).replace(/0$/, "");
};

/**
 * The most a page can cost, in paise.
 *
 * The server has the same rule, and the reason is the same: the price
 * of an order is pages x copies x rate, the largest order the platform
 * takes is 300 pages of 100 copies, and the column that holds the price
 * is a 32 bit integer. A rate above this would let a shop price an
 * order the database cannot hold, and the failure would land on the
 * customer who tried to order.
 */
export const MAX_RATE_PAISE = 50_000;
// The server has the same number, in backend/app/domain/limits.py, and
// it is the one that matters: the server refuses a rate above it.
