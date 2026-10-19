import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router";

import {
  createOrder,
  getOrder,
  simulatePayment,
  type OrderDetailResponse,
  type OrderResponse,
} from "../../api/orders";
import type { UploadResponse } from "../../api/client";
import { Alert, Button } from "../../components/ui";
import { messageForError } from "../../lib/errors";
import { formatPaise } from "../../lib/money";
import { openCheckout } from "../../lib/razorpay";
import {
  describeOptions,
  type OptionsFormValues,
  type PaymentMethod,
} from "./schemas";

type Shop = {
  id: string;
  name: string;
  address: string;
};

type Quote = {
  price_paise: number;
  rate_paise: number;
  min_order_paise: number;
};

type PayStepProps = {
  upload: UploadResponse;
  options: OptionsFormValues;
  shop: Shop;
  quote: Quote;
  paymentMethod: PaymentMethod;
  // Whether the platform is offering paying at the shop at all. The
  // server is the authority, so the choice is only shown when the server
  // says it is on.
  cashAtStoreEnabled: boolean;
  onPaymentMethodChange: (method: PaymentMethod) => void;
  onBack: () => void;
  deadlineMs?: number;
};

type Phase =
  | { kind: "review" }
  | { kind: "paying" }
  | { kind: "confirming"; orderId: string }
  | { kind: "paid"; order: OrderDetailResponse }
  // A cash order is booked straight away. There is no provider to wait
  // for, so there is nothing to poll and nothing to confirm.
  | { kind: "reserved"; order: OrderResponse }
  | { kind: "unconfirmed"; orderId: string }
  | { kind: "failed"; message: string };

const POLL_INTERVAL_MS = 2000;
const POLL_DEADLINE_MS = 60_000;

function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `order-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function PayStep({
  upload,
  options,
  shop,
  quote,
  paymentMethod,
  cashAtStoreEnabled,
  onPaymentMethodChange,
  onBack,
  deadlineMs = POLL_DEADLINE_MS,
}: PayStepProps) {
  const [phase, setPhase] = useState<Phase>({ kind: "review" });
  const idempotencyKey = useRef(newIdempotencyKey());

  const poll = useCallback(async (orderId: string, deadline: number) => {
    while (Date.now() <= deadline) {
      try {
        const detail = await getOrder(orderId);
        if (detail.order.status === "PAID") {
          setPhase({ kind: "paid", order: detail });
          return;
        }
        if (
          detail.order.status === "CANCELLED" ||
          detail.order.status === "EXPIRED"
        ) {
          setPhase({
            kind: "failed",
            message: "This order was closed before the payment landed.",
          });
          return;
        }
      } catch {
        // Keep polling; a transient failure must not lose the order.
      }
      await new Promise((resolve) => {
        setTimeout(resolve, POLL_INTERVAL_MS);
      });
    }
    setPhase({ kind: "unconfirmed", orderId });
  }, []);

  useEffect(() => {
    if (phase.kind !== "confirming") return;
    const timer = setTimeout(() => {
      void poll(phase.orderId, Date.now() + deadlineMs);
    }, 0);
    return () => clearTimeout(timer);
  }, [phase, poll, deadlineMs]);

  const startPayment = async () => {
    setPhase({ kind: "paying" });
    try {
      const created = await createOrder(
        {
          upload_id: upload.id,
          shop_id: shop.id,
          paper_size: options.paper_size,
          color: options.color,
          duplex: options.duplex,
          copies: options.copies,
          expected_price_paise: quote.price_paise,
          payment_method: paymentMethod,
        },
        idempotencyKey.current,
      );
      const orderId = created.order.id;
      const payment = created.payment;

      // A cash order is already booked. The money changes hands at the
      // counter, so there is no checkout to open and nothing to wait for.
      if (payment.provider === "cash") {
        setPhase({ kind: "reserved", order: created.order });
        return;
      }

      const keyId = payment.key_id ?? null;
      if (payment.provider === "razorpay" && keyId !== null) {
        await openCheckout({
          key: keyId,
          amount: payment.amount_paise,
          order_id: payment.provider_order_id,
          currency: payment.currency,
          name: "Smart Printing Network",
          description: `${upload.page_count} page print job`,
          handler: () => setPhase({ kind: "confirming", orderId }),
          modal: { ondismiss: () => setPhase({ kind: "review" }) },
        });
        return;
      }

      await simulatePayment(orderId);
      setPhase({ kind: "confirming", orderId });
    } catch (error) {
      setPhase({ kind: "failed", message: messageForError(error) });
    }
  };

  if (phase.kind === "reserved") {
    const order = phase.order;
    return (
      <section className="flex flex-col gap-4 rounded-xl border border-hairline bg-canvas p-6">
        <h2 className="font-display text-xl font-semibold text-ink">
          Reserved for you
        </h2>
        <p className="text-sm text-steel">
          Order #{order.order_no} is booked. Show this code at the counter and
          pay {formatPaise(order.price_paise)} in cash when you collect it.
        </p>
        <p className="font-mono text-3xl tracking-[0.3em] text-ink">
          {order.pickup_code}
        </p>
        <div className="flex flex-wrap gap-3">
          <Link
            to={`/orders/${order.id}`}
            className="inline-flex min-h-11 items-center rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white transition-colors duration-150 hover:bg-primary-deep"
          >
            View order
          </Link>
        </div>
      </section>
    );
  }

  if (phase.kind === "paid") {
    const order = phase.order.order;
    return (
      <section className="flex flex-col gap-4 rounded-xl border border-hairline bg-canvas p-6">
        <h2 className="font-display text-xl font-semibold text-ink">
          Payment received
        </h2>
        <p className="text-sm text-steel">
          Order #{order.order_no} is paid. Show this code at the counter.
        </p>
        <p className="font-mono text-3xl tracking-[0.3em] text-ink">
          {order.pickup_code}
        </p>
        <div className="flex flex-wrap gap-3">
          <Link
            to={`/orders/${order.id}`}
            className="inline-flex min-h-11 items-center rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white transition-colors duration-150 hover:bg-primary-deep"
          >
            View order
          </Link>
        </div>
      </section>
    );
  }

  if (phase.kind === "unconfirmed") {
    return (
      <section className="flex flex-col gap-4 rounded-xl border border-hairline bg-canvas p-6">
        <h2 className="font-display text-xl font-semibold text-ink">
          Still confirming your payment
        </h2>
        <Alert>
          We have not heard back from the payment provider yet. Do not pay again
          — this order is still being checked.
        </Alert>
        <div className="flex flex-wrap gap-3">
          <Link
            to={`/orders/${phase.orderId}`}
            className="inline-flex min-h-11 items-center rounded-lg border border-hairline-strong bg-canvas px-4 py-2 text-sm font-medium text-ink transition-colors duration-150 hover:bg-surface"
          >
            Check the order
          </Link>
        </div>
      </section>
    );
  }

  if (phase.kind === "failed") {
    return (
      <section className="flex flex-col gap-4 rounded-xl border border-hairline bg-canvas p-6">
        <h2 className="font-display text-xl font-semibold text-ink">
          We could not start the payment
        </h2>
        <Alert>{phase.message}</Alert>
        <div className="flex flex-wrap gap-3">
          <Button onClick={() => setPhase({ kind: "review" })}>
            Try again
          </Button>
          <Button variant="secondary" onClick={onBack}>
            Back
          </Button>
        </div>
      </section>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <section
        aria-label="Your order"
        className="flex flex-col gap-3 rounded-xl border border-hairline bg-canvas p-6"
      >
        <h2 className="font-display text-xl font-semibold text-ink">
          Review and pay
        </h2>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          <dt className="text-steel">File</dt>
          <dd className="text-ink">
            {upload.original_filename} ·{" "}
            {upload.page_count === 1 ? "1 page" : `${upload.page_count} pages`}
          </dd>
          <dt className="text-steel">Options</dt>
          <dd className="text-ink">{describeOptions(options)}</dd>
          <dt className="text-steel">Shop</dt>
          <dd className="text-ink">
            {shop.name}
            <span className="block text-xs text-steel">{shop.address}</span>
          </dd>
          <dt className="text-steel">Rate</dt>
          <dd className="text-ink">{formatPaise(quote.rate_paise)} per page</dd>
          <dt className="text-steel">Total</dt>
          <dd className="font-mono text-base text-ink">
            {formatPaise(quote.price_paise)}
          </dd>
        </dl>
      </section>

      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium text-ink">
          How would you like to pay?
        </legend>
        <label className="flex min-h-11 cursor-pointer items-center gap-2 rounded-md border border-hairline-strong bg-canvas px-4 py-2 text-sm text-ink has-checked:border-primary has-checked:bg-cream-deeper">
          <input
            type="radio"
            name="payment-method"
            value="online"
            className="accent-primary"
            checked={paymentMethod === "online"}
            onChange={() => onPaymentMethodChange("online")}
          />
          Pay online by card or UPI
        </label>
        {cashAtStoreEnabled && (
          <label className="flex min-h-11 cursor-pointer items-center gap-2 rounded-md border border-hairline-strong bg-canvas px-4 py-2 text-sm text-ink has-checked:border-primary has-checked:bg-cream-deeper">
            <input
              type="radio"
              name="payment-method"
              value="at_store"
              className="accent-primary"
              checked={paymentMethod === "at_store"}
              onChange={() => onPaymentMethodChange("at_store")}
            />
            Pay at the shop in cash when you collect
          </label>
        )}
        {paymentMethod === "at_store" && (
          <p className="text-sm text-steel">
            You pay {formatPaise(quote.price_paise)} in cash at the counter. The
            shop gets the order the same way, and the money changes hands when
            you pick it up.
          </p>
        )}
      </fieldset>

      {phase.kind === "confirming" && (
        <p role="status" className="text-sm text-steel">
          Confirming your payment…
        </p>
      )}

      {phase.kind === "paying" && (
        <p role="status" className="text-sm text-steel">
          Starting the payment…
        </p>
      )}

      <div className="flex flex-wrap gap-3">
        <Button
          onClick={() => void startPayment()}
          pending={phase.kind === "paying"}
          pendingLabel="Starting payment…"
        >
          {paymentMethod === "at_store"
            ? `Reserve for ${formatPaise(quote.price_paise)}`
            : `Pay ${formatPaise(quote.price_paise)}`}
        </Button>
        <Button variant="secondary" onClick={onBack}>
          Back
        </Button>
      </div>
    </div>
  );
}
