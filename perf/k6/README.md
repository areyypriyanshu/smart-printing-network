# The load test

`main.js` exercises the three endpoints the phase 2 gate names:
`POST /quotes`, `GET /shops/search` and `GET /vendor/queue`. It is a
k6 script, and it runs against a local stack only.

## What it needs

1. The stack is running (`make up`), migrated and seeded (`make seed`).
2. `SPN_DEV_AUTH=true` in `.env`, so the script can sign in without the
   identity provider. That setting is refused in production, and so is
   this test.
3. `make perf-seed` if the queue is empty. The NFR is about 200 active
   orders; the endpoint is fast when it has none, which proves nothing.
4. k6, or the `grafana/k6` image.

## Run it

With k6 installed:

```bash
mkdir -p perf/results
k6 run -e BASE_URL=http://localhost:8000 \
  --summary-export=perf/results/baseline.json \
  perf/k6/main.js
```

With Docker on macOS:

```bash
mkdir -p perf/results
docker run --rm -i --add-host=host.docker.internal:host-gateway \
  -v "$PWD:/work" -w /work grafana/k6 \
  run -e BASE_URL=http://host.docker.internal:8000 \
  --summary-export=perf/results/baseline.json \
  perf/k6/main.js
```

On Linux, `--network host` and `-e BASE_URL=http://localhost:8000` are
the usual arrangement.

The thresholds in `main.js` turn a regression into a failed run:

| Endpoint | p95 target |
|---|---:|
| `POST /quotes` | 200 ms |
| `GET /shops/search` | 500 ms (no PRD number; the same order as the queue) |
| `GET /vendor/queue` | 300 ms at 200 active orders |

Any failed request fails the run: `http_req_failed` is held to zero, so a
single 429 or 500 is visible rather than averaged away.

## How the users work

Each virtual user is a separate account. The rate limiter is per
account, so sharing one account would measure the limiter rather than
the endpoint. By default:

- four customers, each quoting once a second and searching every two
  seconds;
- one vendor polling the queue once a second.

That stays inside the router's limits: quotes 60 a minute, shop search
30 a minute and the queue 60 a minute. If a run reports 429s, wait for
the window to pass or raise `CUSTOMERS`. Do not raise the pace for one
account: the refusal is the product working as designed.

The script makes one upload per customer in `setup()`, because a quote
and a priced search both need a file.

## Other knobs

| Variable | Default | Meaning |
|---|---|---|
| `BASE_URL` | `http://localhost:8000` | The API, without `/api/v1` |
| `CUSTOMERS` | `4` | Accounts, and virtual users, for quotes and search |
| `QUOTES_EVERY` | `1` | Seconds each customer waits between quotes |
| `SEARCH_EVERY` | `2` | Seconds each customer waits between searches |
| `QUEUE_EVERY` | `1` | Seconds the vendor waits between queue polls |
| `DURATION` | `30s` | How long each scenario runs |
| `VENDOR_EMAIL` | `vendor1@example.com` | The seeded vendor whose queue is read |

The numbers from the run on 2026-10-22 are in
[`../BASELINE.md`](../BASELINE.md). The `--summary-export` file lives in
`perf/results/`, which is ignored because it contains the local sessions
the script made.
