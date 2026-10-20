import { useState } from "react";

import {
  Alert,
  Button,
  pageTitleClassName,
  sectionTitleClassName,
} from "../../components/ui";
import { formatIstDateTime } from "../../lib/dates";
import { messageForError } from "../../lib/errors";
import {
  useAdminActions,
  useAdminShops,
  useShopAction,
  type AdminShop,
  type ShopStatus,
} from "./api";
import { SuspendDialog } from "./suspend-dialog";

const FILTERS: { value: ShopStatus; label: string }[] = [
  { value: "pending", label: "Waiting for a decision" },
  { value: "verified", label: "Verified" },
  { value: "all", label: "All shops" },
];

/**
 * The verification queue.
 *
 * One screen with one job: decide which shops are allowed to take
 * orders. There is no admin view of orders, of money or of customers,
 * and no reason for one to exist yet. The page is deliberately a list and
 * two buttons.
 */
export function AdminShopsPage() {
  const [filter, setFilter] = useState<ShopStatus>("pending");
  const [suspending, setSuspending] = useState<AdminShop | null>(null);
  const shops = useAdminShops(filter);
  const actions = useAdminActions();
  const shopAction = useShopAction();

  const approve = (shop: AdminShop) => {
    shopAction.mutate({ action: "approve", shopId: shop.id });
  };

  const suspend = (reason: string) => {
    if (suspending === null) return;
    shopAction.mutate(
      { action: "suspend", shopId: suspending.id, reason },
      { onSuccess: () => setSuspending(null) },
    );
  };

  // The shop this request is about, so only that row shows a progress
  // label instead of every row on the page.
  const pendingShopId = shopAction.isPending
    ? (shopAction.variables?.shopId ?? null)
    : null;

  return (
    <section className="mx-auto flex w-full max-w-4xl flex-col gap-6 p-6">
      <div className="flex flex-col gap-1">
        <h1 className={pageTitleClassName()}>Shops</h1>
        <p className="text-sm text-steel">
          Approve a shop and it can take orders. Suspending one takes it off the
          market without touching the orders it has already accepted.
        </p>
      </div>

      <div
        role="group"
        aria-label="Filter shops"
        className="flex flex-wrap gap-2"
      >
        {FILTERS.map((option) => (
          <Button
            key={option.value}
            variant={filter === option.value ? "primary" : "secondary"}
            aria-pressed={filter === option.value}
            onClick={() => setFilter(option.value)}
          >
            {option.label}
          </Button>
        ))}
      </div>

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

      {shopAction.isError && <Alert>{messageForError(shopAction.error)}</Alert>}

      {shops.isSuccess && shops.data.items.length === 0 && (
        <div className="rounded-lg border border-hairline-soft bg-canvas p-6">
          <p className="text-sm text-ink">
            {filter === "pending"
              ? "No shops are waiting for a decision."
              : "No shops to show."}
          </p>
        </div>
      )}

      {shops.isSuccess && shops.data.items.length > 0 && (
        <ul className="flex flex-col gap-3">
          {shops.data.items.map((shop) => (
            <li
              key={shop.id}
              className="flex flex-col gap-3 rounded-lg border border-hairline-soft bg-canvas p-5"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="text-base font-medium text-ink">{shop.name}</h2>
                <p className="text-xs text-steel">
                  {shop.is_verified
                    ? shop.accepting_orders
                      ? "Verified, taking orders"
                      : "Verified, not taking orders"
                    : "Waiting for a decision"}
                </p>
              </div>
              <p className="text-sm text-steel">{shop.address}</p>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                <dt className="text-steel">Owner</dt>
                <dd className="text-ink">{shop.owner_full_name}</dd>
                <dt className="text-steel">Email</dt>
                <dd className="text-ink">{shop.owner_email}</dd>
                <dt className="text-steel">Rates</dt>
                <dd className="text-ink">
                  {shop.rate_count === 0
                    ? "None set yet"
                    : `${shop.rate_count} option${shop.rate_count === 1 ? "" : "s"}`}
                </dd>
                <dt className="text-steel">Registered</dt>
                <dd className="text-ink">
                  {formatIstDateTime(shop.created_at)}
                </dd>
              </dl>
              <div className="flex flex-wrap gap-3">
                {shop.is_verified ? (
                  <Button
                    variant="danger"
                    onClick={() => setSuspending(shop)}
                    disabled={shopAction.isPending}
                  >
                    Suspend
                  </Button>
                ) : (
                  <Button
                    onClick={() => approve(shop)}
                    // Only the shop being decided shows the progress
                    // label, and no other shop can be decided at the same
                    // time.
                    pending={pendingShopId === shop.id}
                    pendingLabel="Approving…"
                    disabled={shopAction.isPending}
                  >
                    Approve
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      <section className="flex flex-col gap-3" aria-label="Moderation log">
        <h2 className={sectionTitleClassName()}>Moderation log</h2>
        {actions.isPending && (
          <p role="status" className="text-sm text-steel">
            Loading the log…
          </p>
        )}
        {actions.isError && <Alert>{messageForError(actions.error)}</Alert>}
        {actions.isSuccess && actions.data.items.length === 0 && (
          <p className="text-sm text-steel">Nothing has been decided yet.</p>
        )}
        {actions.isSuccess && actions.data.items.length > 0 && (
          <ul className="flex flex-col gap-2">
            {actions.data.items.map((action) => (
              <li
                key={action.id}
                className="rounded-lg border border-hairline-soft bg-surface p-4 text-sm"
              >
                <p className="text-ink">
                  {action.action === "shop_approved" ? "Approved" : "Suspended"}{" "}
                  <span className="font-medium">{action.shop_name}</span>
                </p>
                <p className="text-xs text-steel">
                  {action.admin_email ?? "From the server command line"} ·{" "}
                  {formatIstDateTime(action.at)}
                </p>
                {action.reason !== null && (
                  <p className="mt-1 text-sm text-steel">{action.reason}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <SuspendDialog
        open={suspending !== null}
        shopName={suspending?.name ?? ""}
        pending={shopAction.isPending}
        error={
          shopAction.isError && suspending !== null ? shopAction.error : null
        }
        onClose={() => setSuspending(null)}
        onConfirm={suspend}
      />
    </section>
  );
}
