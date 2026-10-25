import { useRef, useState } from "react";
import { Link } from "react-router";

import { createOrder, type OrderResponse } from "../../api/orders";
import type { UploadResponse } from "../../api/client";
import {
  Alert,
  Button,
  buttonClassName,
  sectionTitleClassName,
} from "../../components/ui";
import { messageForError } from "../../lib/errors";
import { formatPaise } from "../../lib/money";
import { pickupShareLink } from "../../lib/share";
import { describeOptions, type OptionsFormValues } from "./schemas";

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
  onBack: () => void;
  qualityAcknowledged?: boolean;
};

type Phase =
  | { kind: "review" }
  | { kind: "reserving" }
  // The order is booked and the money is paid at the counter, so there is
  // nothing to wait for and nothing to confirm.
  | { kind: "reserved"; order: OrderResponse }
  | { kind: "failed"; message: string };

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
  onBack,
  qualityAcknowledged = false,
}: PayStepProps) {
  const [phase, setPhase] = useState<Phase>({ kind: "review" });
  const idempotencyKey = useRef(newIdempotencyKey());

  const reserve = async () => {
    setPhase({ kind: "reserving" });
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
          quality_acknowledged: qualityAcknowledged,
        },
        idempotencyKey.current,
      );
      setPhase({ kind: "reserved", order: created.order });
    } catch (error) {
      setPhase({ kind: "failed", message: messageForError(error) });
    }
  };

  if (phase.kind === "reserved") {
    const order = phase.order;
    return (
      <section className="flex flex-col gap-4 rounded-xl border border-hairline bg-canvas p-6">
        <h2 className={sectionTitleClassName()}>Reserved for you</h2>
        <p className="text-sm text-steel">
          Order #{order.order_no} is booked. Show this code at the counter and
          pay {formatPaise(order.price_paise)} in cash when you collect it.
        </p>
        <p className="font-mono text-3xl tracking-[0.3em] text-ink">
          {order.pickup_code}
        </p>
        <p className="text-sm text-steel">
          Somebody else can collect it for you. Anyone with this code can, so
          send it only to the person you trust.
        </p>
        <div className="flex flex-wrap gap-3">
          <Link
            to={`/orders/${order.id}`}
            className={buttonClassName("primary")}
          >
            View order
          </Link>
          <a
            href={pickupShareLink({
              order_no: order.order_no,
              pickup_code: order.pickup_code ?? "",
              shopName: shop.name,
            })}
            target="_blank"
            rel="noopener noreferrer"
            className={buttonClassName("secondary")}
          >
            Share the code on WhatsApp
          </a>
        </div>
      </section>
    );
  }

  if (phase.kind === "failed") {
    return (
      <section className="flex flex-col gap-4 rounded-xl border border-hairline bg-canvas p-6">
        <h2 className={sectionTitleClassName()}>
          We could not reserve this order
        </h2>
        <Alert>{phase.message}</Alert>
        <div className="flex flex-wrap gap-3">
          <Button variant="secondary" onClick={onBack}>
            Back
          </Button>
          <Button onClick={() => setPhase({ kind: "review" })}>
            Try again
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
        <h2 className={sectionTitleClassName()}>Review and reserve</h2>
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
          <dd className="font-mono text-base font-medium text-ink">
            {formatPaise(quote.price_paise)}
          </dd>
        </dl>
        <p className="text-sm text-steel">
          You pay {formatPaise(quote.price_paise)} in cash at the counter when
          you collect. The shop gets the order straight away, and you pay
          nothing unless you pick it up.
        </p>
      </section>

      {phase.kind === "reserving" && (
        <p role="status" className="text-sm text-steel">
          Reserving your order…
        </p>
      )}

      <div className="flex flex-wrap gap-3">
        <Button variant="secondary" onClick={onBack}>
          Back
        </Button>
        <Button
          onClick={() => void reserve()}
          pending={phase.kind === "reserving"}
          pendingLabel="Reserving…"
        >
          Reserve for {formatPaise(quote.price_paise)}
        </Button>
      </div>
    </div>
  );
}
