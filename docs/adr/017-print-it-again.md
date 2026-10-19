# ADR 017: Printing it again copies the file, it does not share it

Date: 2026-10-20
Status: Accepted
Requirement: FR-16 (Sprint 6)

## Context

Academia prints. A student prints the same project report every term:
the same file, a few pages, the same options. Asking them to find the
file again, upload it again and type the options again is asking for
the whole flow to be repeated for a job they have already done.

"Print this again" is the obvious feature. The interesting part is what
the file is allowed to be, because the platform keeps a promise about
files that the feature must not weaken.

The promise (FR-14, file privacy and retention) is that a customer's file is deleted 24 hours after
it is uploaded, and that the shop can open it only through a short-lived
link. That promise is why the platform can say "we do not keep your
documents" and mean it. Anything that lets a customer reopen a file
after the window has passed weakens that promise, and weakening it is
not an option.

There is a second promise in the same area: one upload belongs to one
order. The database says so with `uq_orders_upload_id`.

## Decision

One tap prints it again **while the file is still there**, and after
that the customer is told to upload it again.

The repeat print does not reuse the original upload row. It:

1. copies the stored object to a new storage key,
2. creates a new `uploads` row with its own `delete_after`, 24 hours from
   now,
3. creates a new order with the same options and the same shop, which
   the customer then pays for as usual.

The response carries the new upload id and the options, and the wizard
resumes with them filled in. The customer can change any of it.

After the retention window, `POST /orders/{id}/reorder` answers
`FILE_UNAVAILABLE` with a message that says what to do: upload it once
more. The order detail response carries `file_available`, so the
interface can offer "Print this again" while the file exists and "Upload
it again" after it does.

## Alternatives considered

1. **One order, many reprints.** Rejected: it changes what an order
   means, needs a new status, a new price rule and a way to refund one
   reprint. It also cannot be a single row without a second table, and
   the second table is the thing this design is avoiding.
2. **Point the new order at the same upload row.** Rejected twice over.
   `uq_orders_upload_id` forbids one upload on two orders, and, more
   importantly, the purge job deletes the *object* when the upload's
   `delete_after` passes. The second order would be left pointing at a
   file that is gone, and the customer would find out at the counter.
3. **Keep the file for longer and let the customer reopen it.** Rejected:
   it directly weakens the retention guarantee. The guarantee is worth
   more than the convenience. A student who needs the same file again in
   a month still has it: it is on their own computer.
4. **Do not build it.** Rejected: the request is for a real and common
   case, and the version that respects the retention window is a small
   amount of code.

## Consequences

- The storage gateway grew a `copy_file` operation. It is a server side
  copy in S3, so the bytes do not travel twice, and it is a dictionary
  assignment in the in-memory storage used by the tests.
- A repeat print is a new order with a new price and a new payment. The
  customer pays again, which is right: the shop does the work again.
- The customer's history shows both orders, so "print this again" is
  visible as two orders rather than one order printed twice.
- The 24 hour window is the whole feature's reach. A customer who comes
  back on day three gets the honest answer, not a broken button.
