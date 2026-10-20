# ADR 021: The dialogs use the native `dialog` element, not Radix

Date: 2026-01-05
Status: Accepted
Requirement: quality (no requirement id, a project wide convention)

## Context

`docs/FRONTEND_GUIDELINES.md` said to build dialogs, selects and tabs on
Radix primitives for correct focus handling and ARIA. The code had
already done something else: the dialogs are built on the native
`<dialog>` element.

The guideline was not wrong to want focus handling. A dialog that does
not trap focus, does not close on Escape, and leaves the page behind it
clickable is broken, and getting that right from scratch is where a
library earns its place. The question was only whether the native
element was good enough, and the code had already answered it.

The native element gives all of it: `showModal()` traps focus, Escape
fires `cancel`, the rest of the page becomes inert, and the dialog
renders in the top layer over everything. The component also handles
the case where `showModal` does not exist, by falling back to the `open`
attribute, so it still works in the test environment.

## Decision

Keep the native `<dialog>`, and correct the guideline to say so.

The reasoning for keeping it:

1. **No new dependency.** Radix is several packages for behaviour the
   browser now provides. `AGENTS.md` requires a justification and an
   ADR for a new dependency, and "it is nicer" is not one.
2. **Less code.** The dialog component is about ninety lines and has no
   focus trap of its own to get wrong.
3. **The behaviour is the browser's.** Focus trapping and the inert
   background are not reimplemented, so they behave the way the platform
   defines them.

The guideline is the thing that was wrong, because it described a stack
the project does not use. It now says native `<dialog>`, and says why.

## Alternatives considered

1. **Radix, as the guideline said.** Rejected: it adds a dependency for
   behaviour the platform provides, and the existing implementation was
   already correct and tested.
2. **A hand written focus trap.** Rejected: it is the most common way
   for a dialog to become unusable for a keyboard user, and the native
   element does it properly.
3. **No dialogs at all.** Rejected: rejecting an order needs a reason,
   and a reason needs a text field, so a dialog is the right shape.
4. **Leave the guideline and the code disagreeing.** Rejected: the next
   person to read the guidelines would either add Radix or would be
   confused. `AGENTS.md` asks for the disagreement to be resolved
   explicitly, in the open.

## Consequences

- The dependency list stays as it is, and the bundle does not grow.
- The guideline and the code now say the same thing.
- The `Dialog` component is still the only place that knows how a dialog
  works, so a screen cannot get the focus behaviour wrong by building
  its own.
- If a dialog ever needs something the native element does not do, a
  library becomes worth its cost, and this ADR is the place to say so.
