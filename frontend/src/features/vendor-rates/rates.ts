import { z } from "zod";

import type { RateItem } from "../../api/client";
import {
  MAX_RATE_PAISE,
  formatPaiseForInput,
  isValidRupeesInput,
  parseRupeesToPaise,
} from "../../lib/money";
import { PAPER_SIZES, type PaperSize } from "../../lib/paper";

export type RateRow = {
  paper_size: PaperSize;
  color: boolean;
  duplex: boolean;
  rupees: string;
};

export function emptyRateRows(): RateRow[] {
  const rows: RateRow[] = [];
  for (const paper_size of PAPER_SIZES) {
    for (const color of [false, true]) {
      for (const duplex of [false, true]) {
        rows.push({ paper_size, color, duplex, rupees: "" });
      }
    }
  }
  return rows;
}

const rowKey = (row: {
  paper_size: string;
  color: boolean;
  duplex: boolean;
}): string => `${row.paper_size}|${row.color}|${row.duplex}`;

export function rowsFromRateItems(items: RateItem[]): RateRow[] {
  const byKey = new Map(items.map((item) => [rowKey(item), item]));
  return emptyRateRows().map((row) => {
    const item = byKey.get(rowKey(row));
    return item === undefined
      ? row
      : { ...row, rupees: formatPaiseForInput(item.rate_paise) };
  });
}

export function rowsToRateItems(rows: RateRow[]): RateItem[] {
  const items: RateItem[] = [];
  for (const row of rows) {
    if (row.rupees.trim() === "") continue;
    const rate_paise = parseRupeesToPaise(row.rupees);
    if (rate_paise === null) continue;
    items.push({
      paper_size: row.paper_size,
      color: row.color,
      duplex: row.duplex,
      rate_paise,
    });
  }
  return items;
}

export function rowLabel(
  row: Pick<RateRow, "paper_size" | "color" | "duplex">,
): string {
  const color = row.color ? "Colour" : "Black & white";
  const duplex = row.duplex ? "Double-sided" : "Single-sided";
  return `${row.paper_size} · ${color} · ${duplex}`;
}

export const ratesSchema = z.object({
  rows: z
    .array(
      z.object({
        rupees: z
          .string()
          .refine(
            (value) => value.trim() === "" || isValidRupeesInput(value),
            "Enter a positive amount like 2.50",
          )
          .refine((value) => {
            if (value.trim() === "") return true;
            const paise = parseRupeesToPaise(value);
            return paise !== null && paise <= MAX_RATE_PAISE;
          }, "A page cannot cost more than 500 rupees"),
      }),
    )
    .length(8),
});

export type RatesFormValues = z.infer<typeof ratesSchema>;

export function rowsToFormValues(rows: RateRow[]): RatesFormValues {
  return { rows: rows.map((row) => ({ rupees: row.rupees })) };
}
