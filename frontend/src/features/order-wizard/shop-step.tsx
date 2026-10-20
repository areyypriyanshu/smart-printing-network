import { useState } from "react";

import type { UploadResponse } from "../../api/client";
import { Alert, Button } from "../../components/ui";
import { messageForError } from "../../lib/errors";
import { formatPaise } from "../../lib/money";
import { useNearbyShops, useShops } from "../shops";
import { useShopQuotes, type ShopQuote } from "./api";
import { describeOptions, type OptionsFormValues } from "./schemas";

export type ShopSelection = {
  shop: { id: string; name: string; address: string };
  quote: {
    price_paise: number;
    rate_paise: number;
    min_order_paise: number;
  };
};

type ShopStepProps = {
  upload: UploadResponse;
  options: OptionsFormValues;
  selectedShopId: string | null;
  onSelect: (selection: ShopSelection) => void;
  onContinue: () => void;
  onBack: () => void;
};

const UNAVAILABLE_MESSAGES: Record<string, string> = {
  RATE_NOT_SET: "Does not offer these options.",
  SHOP_UNAVAILABLE: "Not taking orders right now.",
};

/** A distance in metres, in words a person would use. */
function formatDistance(metres: number): string {
  if (metres < 1000) return `${metres} m`;
  return `${(metres / 1000).toFixed(1)} km`;
}

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
  onContinue,
  onBack,
}: ShopStepProps) {
  const shops = useShops();
  const [position, setPosition] = useState<{
    latitude: number;
    longitude: number;
  } | null>(null);
  const [locationError, setLocationError] = useState<string | null>(null);
  const nearby = useNearbyShops(
    position === null
      ? null
      : { latitude: position.latitude, longitude: position.longitude },
  );

  // With a position, the nearby shops come first, nearest first. Without
  // one, the whole list is shown as it always was.
  const listed =
    position === null
      ? (shops.data?.items ?? [])
      : (nearby.data?.items ?? shops.data?.items ?? []);
  const quotes = useShopQuotes(upload.id, listed, options);

  const findMe = () => {
    setLocationError(null);
    if (!("geolocation" in navigator)) {
      setLocationError(
        "This browser cannot share a location, so here is every shop we have.",
      );
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (result) => {
        setPosition({
          latitude: result.coords.latitude,
          longitude: result.coords.longitude,
        });
      },
      () => {
        setLocationError(
          "We could not find your location, so here is every shop we have. " +
            "You can still pick one.",
        );
      },
      { timeout: 10_000, maximumAge: 300_000 },
    );
  };

  const sorted = [...quotes].sort((a, b) => {
    if (rank(a) !== rank(b)) return rank(a) - rank(b);
    if (position !== null) {
      // The shop nearest the customer comes first.
      const distanceA = a.shop.distance_m ?? Number.MAX_SAFE_INTEGER;
      const distanceB = b.shop.distance_m ?? Number.MAX_SAFE_INTEGER;
      if (distanceA !== distanceB) return distanceA - distanceB;
    }
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

      {shops.isSuccess && (
        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="secondary"
            onClick={findMe}
            pending={nearby.isFetching}
            pendingLabel="Looking…"
          >
            {position === null ? "Find shops near me" : "Showing shops near me"}
          </Button>
          {position !== null && (
            <Button variant="secondary" onClick={() => setPosition(null)}>
              Show all shops
            </Button>
          )}
        </div>
      )}

      {locationError !== null && (
        <p role="status" className="text-sm text-steel">
          {locationError}
        </p>
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
                    <p className="font-mono text-lg font-medium text-ink">
                      {formatPaise(state.quote.price_paise)}
                    </p>
                  )}
                </div>
                <p className="text-sm text-steel">{shop.address}</p>

                {shop.distance_m !== null && shop.distance_m !== undefined && (
                  <p className="text-xs text-steel">
                    {formatDistance(shop.distance_m)} away
                  </p>
                )}

                {shop.phone != null && (
                  <p className="text-xs text-steel">
                    Phone:{" "}
                    <a
                      href={`tel:${shop.phone.replace(/[^0-9+]/g, "")}`}
                      className="font-medium text-ink underline"
                    >
                      {shop.phone}
                    </a>
                  </p>
                )}

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
                        onClick={() =>
                          onSelect({
                            shop: {
                              id: shop.id,
                              name: shop.name,
                              address: shop.address,
                            },
                            quote: {
                              price_paise: state.quote.price_paise,
                              rate_paise: state.quote.rate_paise,
                              min_order_paise: state.quote.min_order_paise,
                            },
                          })
                        }
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
        </section>
      )}

      <div className="flex flex-wrap gap-3">
        <Button variant="secondary" onClick={onBack}>
          Back
        </Button>
        {selected !== undefined && selected.state.status === "ok" && (
          <Button onClick={onContinue}>Continue to payment</Button>
        )}
      </div>
    </div>
  );
}
