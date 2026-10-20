import { useState } from "react";

import { Alert, Button, Dialog, Textarea } from "../../components/ui";
import { messageForError } from "../../lib/errors";

export type ReasonAction = "reject" | "cancel";

type ReasonDialogProps = {
  open: boolean;
  action: ReasonAction;
  orderNumber: number;
  pending: boolean;
  error: unknown;
  onClose: () => void;
  onConfirm: (reason: string) => void;
};

const COPY: Record<
  ReasonAction,
  { title: string; description: string; cta: string; pending: string }
> = {
  reject: {
    title: "Reject this order",
    description:
      "The customer is refunded. They see your reason, so keep it short and useful.",
    cta: "Reject order",
    pending: "Rejecting…",
  },
  cancel: {
    title: "Cancel this order",
    description:
      "You already accepted this one, so the customer is refunded. They see your reason.",
    cta: "Cancel order",
    pending: "Cancelling…",
  },
};

export function ReasonDialog({
  open,
  action,
  orderNumber,
  pending,
  error,
  onClose,
  onConfirm,
}: ReasonDialogProps) {
  const [reason, setReason] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const copy = COPY[action];

  const close = () => {
    setReason("");
    setValidationError(null);
    onClose();
  };

  const submit = () => {
    if (reason.trim() === "") {
      setValidationError("Give the customer a reason.");
      return;
    }
    setValidationError(null);
    onConfirm(reason.trim());
  };

  return (
    <Dialog
      open={open}
      onClose={close}
      title={copy.title}
      description={`Order #${orderNumber}. ${copy.description}`}
      footer={
        <>
          <Button variant="secondary" onClick={close} disabled={pending}>
            Keep the order
          </Button>
          <Button
            variant="danger"
            pending={pending}
            pendingLabel={copy.pending}
            onClick={submit}
          >
            {copy.cta}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-2">
        <label htmlFor="reason" className="text-sm font-medium text-ink">
          Reason
        </label>
        <Textarea
          id="reason"
          name="reason"
          rows={3}
          value={reason}
          maxLength={500}
          placeholder="For example: out of colour toner"
          aria-invalid={validationError !== null}
          aria-describedby={
            validationError !== null ? "reason-error" : undefined
          }
          onChange={(event) => setReason(event.target.value)}
        />
        {validationError !== null && (
          <p id="reason-error" role="alert" className="text-sm text-danger">
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
