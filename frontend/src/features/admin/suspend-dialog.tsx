import { useState } from "react";

import { Alert, Button, Dialog, Textarea } from "../../components/ui";
import { messageForError } from "../../lib/errors";

type SuspendDialogProps = {
  open: boolean;
  shopName: string;
  pending: boolean;
  error: unknown;
  onClose: () => void;
  onConfirm: (reason: string) => void;
};

/**
 * Why a shop is being taken off the market.
 *
 * The reason is not decoration. It goes into the moderation log, and it
 * is the first thing anybody reads when a shop is questioned later. It
 * is also the only place the customer-facing consequence is explained:
 * taking a shop offline does not touch the orders it has already
 * accepted, because a customer who already paid is owed that printout.
 */
export function SuspendDialog({
  open,
  shopName,
  pending,
  error,
  onClose,
  onConfirm,
}: SuspendDialogProps) {
  const [reason, setReason] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  const close = () => {
    setReason("");
    setValidationError(null);
    onClose();
  };

  const submit = () => {
    if (reason.trim() === "") {
      setValidationError("Give a reason. It goes into the moderation log.");
      return;
    }
    setValidationError(null);
    onConfirm(reason.trim());
  };

  return (
    <Dialog
      open={open}
      onClose={close}
      title={`Suspend ${shopName}`}
      description="The shop stops appearing to customers and cannot take new orders. The orders it has already accepted are left alone, because a customer who has paid is owed that printout."
      footer={
        <>
          <Button variant="secondary" onClick={close} disabled={pending}>
            Keep the shop
          </Button>
          <Button
            variant="danger"
            pending={pending}
            pendingLabel="Suspending…"
            onClick={submit}
          >
            Suspend shop
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-2">
        <label
          htmlFor="suspend-reason"
          className="text-sm font-medium text-ink"
        >
          Reason
        </label>
        <Textarea
          id="suspend-reason"
          name="suspend-reason"
          rows={3}
          value={reason}
          maxLength={500}
          placeholder="For example: the owner could not be reached at the address"
          aria-invalid={validationError !== null}
          aria-describedby={
            validationError !== null ? "suspend-reason-error" : undefined
          }
          onChange={(event) => setReason(event.target.value)}
        />
        {validationError !== null && (
          <p
            id="suspend-reason-error"
            role="alert"
            className="text-sm text-danger"
          >
            {validationError}
          </p>
        )}
        {error !== null && error !== undefined && (
          <Alert>{messageForError(error)}</Alert>
        )}
      </div>
    </Dialog>
  );
}
