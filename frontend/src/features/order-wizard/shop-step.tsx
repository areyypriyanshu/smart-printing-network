import type { UploadResponse } from "../../api/client";
import { Alert, Button } from "../../components/ui";
import { messageForError } from "../../lib/errors";
import { formatPaise } from "../../lib/money";
import { useShops } from "../shops/api";
import { useShopQuotes, type ShopQuote } from "./api";
import { describeOptions, type OptionsFormValues } from "./schemas";

type ShopStepProps = {
  upload: UploadResponse;
  options: OptionsFormValues;
  selectedShopId: string | null;
  onSelect: (shopId: string) => void;
  onBack: () => void;
};

const UNAVAILABLE_MESSAGES: Record<string, string> = {
  RATE_NOT_SET: "Does not offer these options.",
  SHOP_UNAVAILABLE: "Not taking orders right now.",
};

function rank(quote: ShopQuote): number {
  if (quote.state.status === "ok") return 0;
  if (quote.state.status === "pending") return 1;
  return 2;
}

export function ShopStep({
  upload,
  options,
  selectedShopId,
  onSelect,
  onBack,
}: ShopStepProps) {
  const shops = useShops();
  const quotes = useShopQuotes(upload.id, shops.data?.items ?? [], options);

  const sorted = [...quotes].sort((a, b) => {
    if (rank(a) !== rank(b)) return rank(a) - rank(b);
    if (a.state.status === "ok" && b.state.status === "ok") {
      return a.state.quote.price_paise - b.state.quote.price_paise;
    }
    return 0;
  });

  const selected = sorted.find(
    (quote) => quote.shop.id === selectedShopId && quote.state.status === "ok",
  );

  return (
    <div className="flex flex-col gap-4">
      {shops.isPending && (
        <p role="status" className="text-sm text-steel">
          Loading shops…
        </p>
      )}

      {shops.isError && (
        <div className="flex flex-col gap-3">
          <Alert>{messageForError(shops.error)}</Alert>
          <div>
            <Button variant="secondary" onClick={() => void shops.refetch()}>
              Try again
            </Button>
          </div>
        </div>
      )}

      {shops.isSuccess && sorted.length === 0 && (
        <div className="rounded-lg border border-hairline-soft bg-canvas p-6">
          <p className="text-sm text-ink">No verified shops yet.</p>
          <p className="mt-1 text-sm text-steel">
            Shops appear here after they are verified. Please check back soon.
          </p>
        </div>
      )}

      {sorted.length > 0 && (
        <>
          <p className="text-sm text-steel">
            Prices for{" "}
            {upload.page_count === 1 ? "1 page" : `${upload.page_count} pages`},{" "}
            {describeOptions(options)}.
          </p>
          <ul className="flex flex-col gap-3">
            {sorted.map(({ shop, state }) => (
              <li
                key={shop.id}
                className="flex flex-col gap-2 rounded-lg border border-hairline-soft bg-canvas p-5"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h3 className="text-base font-medium text-ink">
                    {shop.name}
                  </h3>
                  {state.status === "ok" && (
                    <p className="text-lg font-medium text-ink">
                      {formatPaise(state.quote.price_paise)}
                    </p>
                  )}
                </div>
                <p className="text-sm text-steel">{shop.address}</p>

                {state.status === "pending" && (
                  <p className="text-sm text-steel">Checking price…</p>
                )}

                {state.status === "unavailable" && (
                  <p className="text-sm text-steel">
                    {UNAVAILABLE_MESSAGES[state.code] ?? "Not available."}
                  </p>
                )}

                {state.status === "error" && (
                  <p className="text-sm text-steel">
                    {messageForError(state.error)}
                  </p>
                )}

                {state.status === "ok" && (
                  <>
                    <p className="text-xs text-steel">
                      {formatPaise(state.quote.rate_paise)} per page
                      {state.quote.min_order_paise > 0 &&
                        ` · minimum order ${formatPaise(state.quote.min_order_paise)}`}
                    </p>
                    {state.quote.price_paise === state.quote.min_order_paise &&
                      state.quote.min_order_paise > 0 && (
                        <p className="text-xs text-steel">
                          Minimum order applies.
                        </p>
                      )}
                    <div>
                      <Button
                        variant={
                          shop.id === selectedShopId ? "secondary" : "primary"
                        }
                        onClick={() => onSelect(shop.id)}
                      >
                        {shop.id === selectedShopId
                          ? "Selected"
                          : "Choose this shop"}
                      </Button>
                    </div>
                  </>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      {selected !== undefined && selected.state.status === "ok" && (
        <section
          aria-label="Your selection"
          className="flex flex-col gap-2 rounded-lg border-2 border-primary bg-cream p-6"
        >
          <h3 className="text-base font-medium text-ink">Your selection</h3>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
            <dt className="text-steel">File</dt>
            <dd className="text-ink">
              {upload.original_filename} ·{" "}
              {upload.page_count === 1
                ? "1 page"
                : `${upload.page_count} pages`}
            </dd>
            <dt className="text-steel">Options</dt>
            <dd className="text-ink">{describeOptions(options)}</dd>
            <dt className="text-steel">Shop</dt>
            <dd className="text-ink">{selected.shop.name}</dd>
            <dt className="text-steel">Price</dt>
            <dd className="font-medium text-ink">
              {formatPaise(selected.state.quote.price_paise)}
            </dd>
          </dl>
          <p className="text-xs text-steel">
            Order review and payment arrive in the next milestone of this
            project.
          </p>
        </section>
      )}

      <div>
        <Button variant="secondary" onClick={onBack}>
          Back
        </Button>
      </div>
    </div>
  );
}
