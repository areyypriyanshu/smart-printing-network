/**
 * The one style for a page title.
 *
 * Every screen has exactly one `h1`, and they all look the same. The
 * class used to be written out by hand in nine places, and three
 * different recipes had grown up, so two screens drifted apart.
 */
export function pageTitleClassName(className?: string): string {
  return [
    "font-display text-2xl font-bold tracking-tight text-ink",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");
}

/**
 * The one style for a heading inside a page.
 *
 * A card, a panel and a section all use this, so a screen never mixes
 * three different heading sizes.
 */
export function sectionTitleClassName(className?: string): string {
  return ["font-display text-lg font-semibold text-ink", className ?? ""]
    .filter(Boolean)
    .join(" ");
}
