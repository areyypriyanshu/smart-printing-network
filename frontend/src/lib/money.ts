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
