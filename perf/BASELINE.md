# Phase 2 load baseline

Measured on 2026-10-22 against the local Docker Compose stack, on the
sprint 8 working tree whose base commit was `92bdd63`.

This is a baseline, not a benchmark of production hardware. The API and
the frontend run as containers on an Apple Silicon laptop, and the
PostGIS image runs under Rosetta emulation. The numbers are useful for
one question: does a change make an endpoint slower than it was?

## What was running

- One API container, one worker, one PostgreSQL 16 / PostGIS 3.6 container.
- Three seeded shops, one seeded customer.
- **238 active orders** in the vendor queue: the 200 made by
  `perf/seed_queue.py` (cash orders, labelled `perf-load-`) plus 38 left
  by the end-to-end suite.
- Four customer accounts, one per virtual user, and the seeded vendor
  account.
- The load script ran for 30 seconds. Each run made 120 quote
  requests, 60 searches and 30 queue requests; no request failed in
  either run.

## Results

Two runs on the same machine are recorded, because a single run on a
laptop is a sample and not a stable number. Both passed every threshold.

| Endpoint | Requests per run | Run 1 p95 | Run 2 p95 | PRD target |
|---|---:|---:|---:|---:|
| `POST /quotes` | 120 | 25.4 ms | 25.8 ms | p95 < 200 ms |
| `GET /shops/search` | 60 | 137.2 ms | 133.1 ms | no number; held to 500 ms |
| `GET /vendor/queue` | 30 | 61.0 ms | 28.4 ms | p95 < 300 ms with 200 active orders |

`http_req_failed` was 0.00% in both runs.

The queue number moved most between runs (61.0 ms and 28.4 ms), which is
what a laptop does when another container takes the processor for a
moment. The quote is stable because it is one row and one calculation.
The search is the slowest of the three because it does the most work:
the spatial query, the rate join and a price for every shop. The first
search in a run can be slower than the rest while the database warms its
pages.

## Index review

`perf/explain-review.sql` adds the rows in a transaction and rolls them
back. The plans below come from that run, with 2,000 shops around
Kolkata and 20,200 orders (200 active, 20,000 finished) for one shop.

**Shop search, distance order.** The planner used the spatial index:

```text
Bitmap Index Scan on shops_location_gix
  Index Cond: (location && _st_expand(point, 5000))
  rows=500
```

The filter is `ST_DWithin` on the geography column, which is what the
index was made for. 373 of the 500 candidate shops were inside the
radius; the rest were removed by the filter. Execution time was 43.6 ms
for 2,000 shops.

**Shop search, price order.** The same spatial index selected the
candidate shops, then the rate was joined and the price sorted:

```text
Bitmap Index Scan on shops_location_gix
  Index Cond: (location && _st_expand(point, 5000))
  rows=500
```

Execution time was 84.9 ms. The rate join is a nested loop in this
plan because `shop_rates` is small in the fixture. A shop count in the
tens of thousands would need a fresh `EXPLAIN`; this fixture does not
claim otherwise.

**Vendor queue.** The partial index was used, and the finished orders
were never touched:

```text
Index Scan using orders_queue_idx on orders
  Index Cond: (shop_id = ...)
  rows=238
```

The index is `(shop_id, status, reserved_at) WHERE status IN (active)`,
which is the filter and the order the queue uses. Execution time was
0.21 ms for the 238 active rows out of 20,438.

## How to reproduce

```bash
make up
make migrate
make seed
make perf-seed                    # 200 reserved orders for vendor1's shop
make perf-explain                 # prints the plans above and rolls back
```

The load test needs the local way in, because it refuses to run against
a deployment:

```bash
# .env
SPN_DEV_AUTH=true

docker compose up -d
mkdir -p perf/results
docker run --rm -i --add-host=host.docker.internal:host-gateway \
  -v "$PWD:/work" -w /work grafana/k6 \
  run -e BASE_URL=http://host.docker.internal:8000 \
  --summary-export=perf/results/baseline.json \
  perf/k6/main.js
```

The k6 threshold fails the run if a p95 crosses its target or if any
request fails. A 429 means the script asked one account for more than
its rate limit allows; wait a minute, or raise `CUSTOMERS`, rather than
raising the pace for one account.

The `--summary-export` line writes the raw summary under
`perf/results/`. That directory is ignored, because the summary contains
the local sessions the script made.
