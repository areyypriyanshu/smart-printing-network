/**
 * The one style for a link that sits inside a sentence.
 *
 * There used to be four different treatments for the same role, and one
 * of them carried no focus ring at all. A link in prose is a link
 * wherever it appears, so it looks the same everywhere.
 */
export function linkClassName(className?: string): string {
  return [
    "font-medium text-primary underline underline-offset-2 transition-colors duration-150",
    "hover:text-primary-deep",
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");
}
