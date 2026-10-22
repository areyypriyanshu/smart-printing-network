import { zodResolver } from "@hookform/resolvers/zod";
import { useState, type ChangeEvent, type FormEvent } from "react";
import { useForm, useWatch } from "react-hook-form";
import { useNavigate } from "react-router";

import { ApiError, type UploadResponse } from "../../api/client";
import { uploadPdf } from "../../api/upload";
import {
  Alert,
  Button,
  pageTitleClassName,
  sectionTitleClassName,
} from "../../components/ui";
import { messageForError } from "../../lib/errors";
import { formatPaise } from "../../lib/money";
import {
  OPTION_DEFAULTS,
  OptionsFields,
  describeOptions,
  optionsSchema,
  type OptionsFormInput,
  type OptionsFormValues,
} from "../order-wizard";
import {
  useShopSearch,
  type ShopSearchItem,
  type ShopSearchQuery,
} from "./api";

/**
 * The shops around the customer, and what they would charge.
 *
 * The customer can say where they are in two ways: the browser can
 * share a location, or they can type an area. Either way the server
 * does the finding, and a customer who says neither still gets the
 * whole list.
 *
 * The prices are the server's. They come from the same function the
 * order flow uses, so the number on this page is the number the
 * customer is charged.
 */

const RADII: { value: number; label: string }[] = [
  { value: 1000, label: "1 km" },
  { value: 2000, label: "2 km" },
  { value: 5000, label: "5 km" },
  { value: 10000, label: "10 km" },
  { value: 25000, label: "25 km" },
];

const MAX_UPLOAD_MB = 50;

type SortMode = "auto" | "distance" | "price";

/** A distance in metres, in words a person would use. */
function formatDistance(metres: number): string {
  if (metres < 1000) return `${metres} m`;
  return `${(metres / 1000).toFixed(1)} km`;
}

export function SearchPage() {
  const navigate = useNavigate();
  const [position, setPosition] = useState<{
    latitude: number;
    longitude: number;
  } | null>(null);
  const [address, setAddress] = useState("");
  const [radius, setRadius] = useState(5000);
  const [sort, setSort] = useState<SortMode>("auto");
  const [upload, setUpload] = useState<UploadResponse | null>(null);
  const [locationError, setLocationError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const {
    register,
    control,
    formState: { errors },
  } = useForm<OptionsFormInput, unknown, OptionsFormValues>({
    resolver: zodResolver(optionsSchema),
    defaultValues: OPTION_DEFAULTS,
  });

  const watched = useWatch({ control });
  const copies = Number(watched.copies);
  const copiesAreUsable =
    Number.isInteger(copies) && copies >= 1 && copies <= 100;
  const options: OptionsFormValues = {
    paper_size: watched.paper_size ?? OPTION_DEFAULTS.paper_size,
    color: watched.color ?? false,
    duplex: watched.duplex ?? false,
    copies: copiesAreUsable ? copies : 1,
  };

  const trimmedAddress = address.trim();
  const hasPlace = position !== null || trimmedAddress !== "";
  const wantsPrices = upload !== null && copiesAreUsable;

  const query: ShopSearchQuery = {
    radius_m: radius,
    limit: 50,
    ...(position !== null
      ? { latitude: position.latitude, longitude: position.longitude }
      : {}),
    ...(position === null && trimmedAddress !== ""
      ? { address: trimmedAddress }
      : {}),
    ...(sort === "price" && wantsPrices
      ? { sort: "price" as const }
      : sort === "distance" && hasPlace
        ? { sort: "distance" as const }
        : {}),
    ...(wantsPrices && upload !== null
      ? {
          upload_id: upload.id,
          paper_size: options.paper_size,
          color: options.color,
          duplex: options.duplex,
          copies: options.copies,
        }
      : {}),
  };
  const shops = useShopSearch(query);

  const findMe = () => {
    setLocationError(null);
    if (!("geolocation" in navigator)) {
      setLocationError(
        "This browser cannot share a location, so here is every shop we have. " +
          "You can type an area instead.",
      );
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (result) => {
        setPosition({
          latitude: result.coords.latitude,
          longitude: result.coords.longitude,
        });
        setAddress("");
        setSort((current) => (current === "auto" ? current : "auto"));
      },
      () => {
        setLocationError(
          "We could not find your location, so here is every shop we have. " +
            "You can type an area instead.",
        );
      },
      { timeout: 10_000, maximumAge: 300_000 },
    );
  };

  const searchTheAddress = (event: FormEvent) => {
    event.preventDefault();
    setLocationError(null);
    setPosition(null);
  };

  const chooseFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file === undefined) return;
    if (file.size === 0) {
      setUploadError("That file is empty.");
      return;
    }
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      setUploadError(`The file is larger than ${MAX_UPLOAD_MB} MB.`);
      return;
    }
    setUploadError(null);
    setUploading(true);
    try {
      const result = await uploadPdf(file, () => {}).promise;
      setUpload(result);
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === "ABORTED") return;
      setUploadError(messageForError(caught));
    } finally {
      setUploading(false);
    }
  };

  const orderFrom = (shop: ShopSearchItem) => {
    navigate("/new", {
      state: {
        ...(upload !== null ? { uploadId: upload.id } : {}),
        ...(upload !== null ? { options } : {}),
        shopId: shop.id,
      },
    });
  };

  return (
    <section className="mx-auto flex w-full max-w-3xl flex-col gap-6 p-6">
      <div className="flex flex-col gap-2">
        <h1 className={pageTitleClassName()}>Find a shop near you</h1>
        <p className="text-sm text-steel">
          See the shops around you and what they would charge for your file.
        </p>
      </div>

      <section
        aria-label="Where you are"
        className="flex flex-col gap-4 rounded-lg border border-beige-deep bg-cream p-6"
      >
        <h2 className={sectionTitleClassName()}>Where you are</h2>

        <div className="flex flex-wrap items-center gap-3">
          <Button variant="secondary" onClick={findMe}>
            {position === null ? "Find shops near me" : "Showing shops near me"}
          </Button>
          {position !== null && (
            <Button
              variant="secondary"
              onClick={() => {
                setPosition(null);
                setSort("auto");
              }}
            >
              Show all shops
            </Button>
          )}
        </div>

        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={searchTheAddress}
        >
          <div className="flex min-w-64 flex-1 flex-col gap-1">
            <label htmlFor="area" className="text-sm font-medium text-ink">
              Or type an area or address
            </label>
            <input
              id="area"
              type="text"
              value={address}
              maxLength={300}
              placeholder="Salt Lake, Kolkata"
              onChange={(event) => {
                setAddress(event.target.value);
                setPosition(null);
                setSort("auto");
              }}
              className="min-h-11 rounded-md border border-hairline-strong bg-canvas px-3 text-sm text-ink"
            />
          </div>
          <Button type="submit" variant="secondary">
            Search this area
          </Button>
        </form>

        {locationError !== null && (
          <p role="status" className="text-sm text-steel">
            {locationError}
          </p>
        )}
      </section>

      <section
        aria-label="What you are printing"
        className="flex flex-col gap-4 rounded-lg border border-beige-deep bg-cream p-6"
      >
        <h2 className={sectionTitleClassName()}>What you are printing</h2>
        <p className="text-sm text-steel">
          A file is optional. With one, every shop shows what it would charge
          for it.
        </p>

        {upload === null ? (
          <div className="flex flex-col gap-2">
            <label
              htmlFor="search-file"
              className="flex min-h-11 cursor-pointer items-center gap-2 rounded-md border border-hairline-strong bg-canvas px-4 py-2 text-sm text-ink has-checked:border-primary"
            >
              <input
                id="search-file"
                type="file"
                accept=".pdf,.docx,.xlsx,.pptx,application/pdf"
                className="sr-only"
                onChange={(event) => void chooseFile(event)}
                disabled={uploading}
              />
              {uploading ? "Uploading…" : "Choose a file to compare prices"}
            </label>
            {uploadError !== null && <Alert>{uploadError}</Alert>}
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <p className="text-sm text-ink">
              {upload.original_filename} ·{" "}
              {upload.page_count === 1
                ? "1 page"
                : `${upload.page_count} pages`}
            </p>
            <div>
              <Button
                variant="secondary"
                onClick={() => {
                  setUpload(null);
                  setSort("auto");
                }}
              >
                Remove the file
              </Button>
            </div>
          </div>
        )}

        {upload !== null && (
          <div className="flex flex-col gap-6">
            <OptionsFields register={register} errors={errors} />
            <p className="text-sm text-steel">
              Prices shown for {describeOptions(options)}.
            </p>
          </div>
        )}
      </section>

      <section aria-label="The shops" className="flex flex-col gap-4">
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex flex-col gap-1">
            <label htmlFor="radius" className="text-sm font-medium text-ink">
              How far
            </label>
            <select
              id="radius"
              value={radius}
              disabled={!hasPlace}
              onChange={(event) => setRadius(Number(event.target.value))}
              className="min-h-11 rounded-md border border-hairline-strong bg-canvas px-3 text-sm text-ink disabled:opacity-60"
            >
              {RADII.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="sort" className="text-sm font-medium text-ink">
              Order by
            </label>
            <select
              id="sort"
              value={sort}
              onChange={(event) => setSort(event.target.value as SortMode)}
              className="min-h-11 rounded-md border border-hairline-strong bg-canvas px-3 text-sm text-ink"
            >
              <option value="auto">Any order</option>
              <option value="distance" disabled={!hasPlace}>
                Nearest first
              </option>
              <option value="price" disabled={!wantsPrices}>
                Cheapest first
              </option>
            </select>
          </div>
        </div>

        {!hasPlace && (
          <p className="text-sm text-steel">
            Share your location or type an area to search by distance.
          </p>
        )}

        {shops.isPending && (
          <p role="status" className="text-sm text-steel">
            Looking for shops…
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

        {shops.isSuccess && shops.data.items.length === 0 && (
          <div className="rounded-lg border border-hairline-soft bg-canvas p-6">
            <p className="text-sm text-ink">
              No shops within {radius / 1000} km.
            </p>
            <p className="mt-1 text-sm text-steel">
              Try a wider radius, or search another area.
            </p>
          </div>
        )}

        {shops.isSuccess && shops.data.items.length > 0 && (
          <ul className="flex flex-col gap-3">
            {shops.data.items.map((shop) => (
              <li
                key={shop.id}
                className="flex flex-col gap-2 rounded-lg border border-hairline-soft bg-canvas p-5"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h3 className="text-base font-medium text-ink">
                    {shop.name}
                  </h3>
                  {shop.price_paise != null && (
                    <p className="font-mono text-lg font-medium text-ink">
                      {formatPaise(shop.price_paise)}
                    </p>
                  )}
                </div>
                <p className="text-sm text-steel">{shop.address}</p>

                {shop.distance_m != null && (
                  <p className="text-xs text-steel">
                    {formatDistance(shop.distance_m)} away
                  </p>
                )}

                {shop.rate_paise != null && (
                  <p className="text-xs text-steel">
                    {formatPaise(shop.rate_paise)} per page
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

                <div>
                  <Button variant="secondary" onClick={() => orderFrom(shop)}>
                    Order from this shop
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </section>
  );
}
