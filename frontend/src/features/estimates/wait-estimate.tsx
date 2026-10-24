import type { WaitEstimateResponse } from "../../api/client";
import { Button } from "../../components/ui";
import { useWaitEstimate } from "./api";

type WaitEstimateProps = {
  estimate?: WaitEstimateResponse | null;
  pending?: boolean;
  error?: boolean;
  onRetry?: () => void;
  onOrderPage?: boolean;
};

/** A shop-level range, never a promise about a particular order's ready time. */
export function WaitEstimate({
  estimate,
  pending = false,
  error = false,
  onRetry,
  onOrderPage = false,
}: WaitEstimateProps) {
  if (pending) {
    return (
      <p role="status" className="text-xs text-steel">
        Checking current queue wait…
      </p>
    );
  }
  if (error || estimate == null) {
    return (
      <div className="flex flex-wrap items-center gap-2 text-xs text-steel">
        <p role="status">Queue estimate unavailable right now.</p>
        {onRetry !== undefined && (
          <Button variant="secondary" onClick={onRetry}>
            Try again
          </Button>
        )}
      </div>
    );
  }

  const minimum = Math.max(0, Math.floor(estimate.minimum_minutes));
  const maximum = Math.max(minimum, Math.ceil(estimate.maximum_minutes));
  return (
    <section
      aria-label={
        onOrderPage ? "Current queue wait at this shop" : "Queue wait estimate"
      }
      className="flex flex-col gap-1 text-xs text-steel"
    >
      <p className="font-medium text-ink">
        {onOrderPage
          ? "Current queue wait at this shop: "
          : "Current queue wait: "}
        {minimum}–{maximum} min
      </p>
      {minimum === 0 && maximum === 0 && (
        <p>No unfinished print work right now.</p>
      )}
      <p>
        {estimate.rough
          ? `Rough estimate · ${estimate.sample_count}/10 recent jobs`
          : `Based on ${estimate.sample_count} recent print jobs`}
      </p>
      <p>
        For a new order, until printing starts
        {onOrderPage
          ? "; not a promised start time for this order"
          : "—not a ready-time promise"}
        .
      </p>
    </section>
  );
}

export function ShopWaitEstimate({ shopId }: { shopId: string }) {
  const query = useWaitEstimate(shopId);
  return (
    <WaitEstimate
      estimate={query.data}
      pending={query.isPending}
      error={query.isError}
      onRetry={() => void query.refetch()}
      onOrderPage
    />
  );
}
