import { describe, expect, it } from "vitest";

import {
  emptyRateRows,
  ratesSchema,
  rowLabel,
  rowsFromRateItems,
  rowsToFormValues,
  rowsToRateItems,
} from "./rates";

describe("emptyRateRows", () => {
  it("returns the eight paper, colour and duplex combinations with A4 first", () => {
    const rows = emptyRateRows();
    expect(rows).toHaveLength(8);
    expect(rows[0]).toMatchObject({
      paper_size: "A4",
      color: false,
      duplex: false,
    });
    expect(rows[7]).toMatchObject({
      paper_size: "A3",
      color: true,
      duplex: true,
    });
  });
});

describe("rowsToRateItems", () => {
  it("converts rupee inputs to paise and keeps the combination", () => {
    const rows = emptyRateRows();
    rows[0] = { ...rows[0], rupees: "2.50" };
    rows[5] = { ...rows[5], rupees: "18" };

    const items = rowsToRateItems(rows);

    expect(items).toEqual([
      { paper_size: "A4", color: false, duplex: false, rate_paise: 250 },
      { paper_size: "A3", color: false, duplex: true, rate_paise: 1800 },
    ]);
  });

  it("skips empty rows", () => {
    expect(rowsToRateItems(emptyRateRows())).toEqual([]);
  });
});

describe("rowsFromRateItems", () => {
  it("fills matching rows and leaves the rest empty", () => {
    const rows = rowsFromRateItems([
      { paper_size: "A3", color: true, duplex: true, rate_paise: 1500 },
      { paper_size: "A4", color: false, duplex: false, rate_paise: 250 },
    ]);

    expect(rows).toHaveLength(8);
    expect(rows[0].rupees).toBe("2.5");
    expect(rows[7].rupees).toBe("15");
    expect(rows[1].rupees).toBe("");
  });

  it("round-trips through the form values", () => {
    const items = [
      {
        paper_size: "A4" as const,
        color: true,
        duplex: false,
        rate_paise: 500,
      },
      {
        paper_size: "A3" as const,
        color: false,
        duplex: true,
        rate_paise: 1200,
      },
    ];
    const values = rowsToFormValues(rowsFromRateItems(items));
    const rows = emptyRateRows().map((row, index) => ({
      ...row,
      rupees: values.rows[index].rupees,
    }));
    expect(rowsToRateItems(rows)).toEqual(items);
  });
});

describe("rowLabel", () => {
  it("describes each option clearly", () => {
    expect(rowLabel({ paper_size: "A4", color: false, duplex: true })).toBe(
      "A4 · Black & white · Double-sided",
    );
  });
});

describe("ratesSchema", () => {
  it("rejects a non-numeric amount", () => {
    const values = rowsToFormValues(emptyRateRows());
    values.rows[0].rupees = "abc";
    expect(ratesSchema.safeParse(values).success).toBe(false);
  });

  it("accepts empty rows", () => {
    expect(
      ratesSchema.safeParse(rowsToFormValues(emptyRateRows())).success,
    ).toBe(true);
  });
});

describe("ratesSchema", () => {
  it("refuses a page that costs more than the ceiling", () => {
    const rows = emptyRateRows().map(() => ({ rupees: "900" }));
    const result = ratesSchema.safeParse({ rows });
    expect(result.success).toBe(false);
  });

  it("accepts a page at the ceiling", () => {
    const rows = emptyRateRows().map(() => ({ rupees: "500" }));
    const result = ratesSchema.safeParse({ rows });
    expect(result.success).toBe(true);
  });
});
