# ADR 020: One style per role, written down once

Date: 2026-01-05
Status: Accepted
Requirement: quality (no requirement id, a project wide convention)

## Context

A full end to end audit of the interface found nine places that hand
wrote the class names of a button instead of using the shared
`buttonClassName()` helper. Each of them had drifted a little: some were
missing the design system's focus ring, one used a six pixel radius where
every other button used eight, and one omitted the transition.

The same had happened to headings. There were three different recipes for
a page title and four for a heading inside a page, so two screens that
were meant to look alike did not.

The cause is not carelessness. It is that the shared helper was
exported, used on one screen, and then written around on the next, and
nothing made the difference visible. The lint rules do not catch a
duplicated class string, and a reviewer reading nine screens has no
reason to remember the exact focus ring in the eighth.

The same audit found two field errors using `text-red-700`, which
resolves to Tailwind's default red rather than the project's `danger`
token, so those two errors were a slightly different colour from the
other five.

## Decision

Every role has exactly one style, and it is written down once:

- `buttonClassName(variant)` for anything that looks like a button,
  including links that are acting as buttons.
- `linkClassName()` for a link inside a sentence.
- `pageTitleClassName()` for the one `h1` on a screen.
- `sectionTitleClassName()` for a heading inside a screen.

A control does not spell out its own classes. It asks for the style of
its role.

Colours come from the theme. A component never names a colour that a
token already covers, and there is no raw value in a class name. The
elevation tokens were added at the same time, so the one hard coded
`rgb(...)` shadow in the landing page is now `shadow-1`.

## Alternatives considered

1. **A CSS module or a component library.** Rejected: a utility class
   system is already in place, and the problem is duplication, not the
   absence of a system. A library would have replaced one set of
   duplicated strings with a dependency.
2. **A lint rule that bans long class strings.** Rejected: it would
   have to encode which class strings are the good ones, which is the
   same problem with less feedback. A helper is checked by the compiler
   and read by the next person.
3. **Leave it, because the screens look the same already.** Rejected:
   they did not. A nine place difference in a focus ring is invisible in
   a screenshot and obvious to a keyboard user.

## Consequences

- The nine hand written button styles are gone, and with them the eight
  controls that had no brand focus ring.
- A page title is now one line of code in one place, so a new screen
  cannot pick a third recipe by accident.
- A colour that is not in the theme is a deliberate choice rather than a
  default, because the token is right there.
- The helpers are four small functions. That is the whole cost.
