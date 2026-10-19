import { useState } from "react";

import { Alert, Button, Dialog, Input } from "../../components/ui";
import { messageForError } from "../../lib/errors";
import { formatPaise } from "../../lib/money";

type PickupDialogProps = {
  open: boolean;
  orderNumber: number;
  // A cash order is paid at the counter, so the shop has to know how much
  // to take.
  cashAmountPaise: number | null;
  pending: boolean;
  error: unknown;
  onClose: () => void;
  onConfirm: (code: string) => void;
};

export function PickupDialog({
  open,
  orderNumber,
  cashAmountPaise,
  pending,
  error,
  onClose,
  onConfirm,
}: PickupDialogProps) {
  const [code, setCode] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  const close = () => {
    setCode("");
    setValidationError(null);
    onClose();
  };

  const submit = () => {
    if (!/^[0-9]{6}$/.test(code)) {
      setValidationError("Enter the six digit code from the customer.");
      return;
    }
    setValidationError(null);
    onConfirm(code);
  };

  return (
    <Dialog
      open={open}
      onClose={close}
      title="Verify pickup"
      description={
        cashAmountPaise === null
          ? `Order #${orderNumber}. Ask the customer for the code on their order.`
          : `Order #${orderNumber}. Take ${formatPaise(cashAmountPaise)} in cash and ask the customer for the code on their order.`
      }
      footer={
        <>
          <Button variant="secondary" onClick={close} disabled={pending}>
            Not yet
          </Button>
          <Button pending={pending} onClick={submit}>
            Hand over
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-2">
        <label htmlFor="pickup-code" className="text-sm font-medium text-ink">
          Pickup code
        </label>
        <Input
          id="pickup-code"
          name="code"
          value={code}
          inputMode="numeric"
          autoComplete="off"
          maxLength={6}
          placeholder="123456"
          className="font-mono text-lg tracking-[0.3em]"
          aria-invalid={validationError !== null}
          aria-describedby={
            validationError !== null ? "pickup-code-error" : undefined
          }
          onChange={(event) =>
            setCode(event.target.value.replace(/[^0-9]/g, "").slice(0, 6))
          }
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              submit();
            }
          }}
        />
        {validationError !== null && (
          <p
            id="pickup-code-error"
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
