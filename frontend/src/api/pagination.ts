/** Collect a cursor-paginated response for screens that present a full list. */
export async function collectAllPages<
  TItem,
  TPage extends { items: TItem[]; next_cursor: string | null },
>(fetchPage: (cursor?: string) => Promise<TPage>): Promise<TPage> {
  const first = await fetchPage();
  const items = [...first.items];
  const seenCursors = new Set<string>();
  let cursor = first.next_cursor;
  while (cursor !== null) {
    if (seenCursors.has(cursor)) {
      throw new Error("The shop list returned a repeated page cursor");
    }
    seenCursors.add(cursor);
    const page = await fetchPage(cursor);
    items.push(...page.items);
    cursor = page.next_cursor;
  }
  return { ...first, items, next_cursor: null };
}
