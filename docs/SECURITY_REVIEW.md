# Final security pass (Sprint 11)

Performed on 2026-10-25 against commit `fde2ae1` plus the Sprint 11
changes. This is a review of the code and configuration in this
repository, not a third-party penetration test. It records what was
checked, the command that produced the evidence, and what remains.

## Result

No critical or high severity finding. The money, authorization and file
paths still hold the rules in `AGENTS.md`. Four residual risks are
listed at the end; none is a code defect introduced by this sprint.

## Evidence

| Check | Command | Result |
|---|---|---|
| Python dependencies | `cd backend && uv run pip-audit` | No known vulnerabilities. `spn-backend` itself is skipped because it is not published to PyPI. |
| JavaScript dependencies | `cd frontend && npm audit` | 0 vulnerabilities (production and development). |
| Secrets in git history | `gitleaks git --redact --no-banner` (v8.30.1) | 122 commits, 3.56 MB scanned, no leaks. |
| Static checks | `make check` and CI | Ruff, mypy strict, import contracts, ESLint, TypeScript. |
| Secret scan in CI | `.github/workflows/ci.yml`, `secrets` job | gitleaks on every push and pull request. |
| Dependency scan in CI | `.github/workflows/ci.yml`, `backend` and `frontend` jobs | `pip-audit` and `npm audit --omit=dev` on every push and pull request. Added in this sprint. |

## What was reviewed

### Transport and browser policy

- One origin serves the app, the API and the WebSocket. Caddy terminates
  TLS and reverse-proxies `/api/*` and `/ws/*`; there is no second public
  listener.
- No `CORSMiddleware` is registered. The application never relies on
  cross-origin browser access.
- Token origin is checked in two places: the Clerk verifier refuses a
  token minted for another application, and the WebSocket route checks
  the `Origin` header against `CLERK_ALLOWED_ORIGINS`.
- Production refuses to start without `CLERK_ALLOWED_ORIGINS`,
  `CLERK_FAPI_URL`, `CLERK_SECRET_KEY` and
  `CLERK_WEBHOOK_SIGNING_SECRET`.
- `infra/Caddyfile` sends HSTS, `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, a strict referrer policy, a permission policy
  that allows geolocation only for this origin, and a content security
  policy.
- The CSP has `object-src 'none'`, `base-uri 'self'`, `form-action
  'self'` and `frame-ancestors 'none'`. Third-party sources are limited
  to Razorpay, the identity provider, Google Maps, Google Fonts and the
  identity provider's fraud-protection widget. `'unsafe-inline'` for
  styles and `'unsafe-eval'` plus `data:` for the fraud widget are
  required by those providers and are commented in the Caddyfile.

### Cookies and sessions

- The application sets no cookies. It authenticates with a bearer token
  that the frontend obtains from the identity provider; the token is
  checked on every request. There is no refresh cookie to scope, because
  there is no first-party refresh flow.
- Account state is read from the database on every authenticated
  request, so deactivating an account takes effect immediately rather
  than at token expiry.

### Object storage

- The bucket is private. No code sets an ACL or a public bucket policy,
  and no upload key is derived from a user-supplied name: keys are
  random UUID-based paths.
- Downloads are presigned GET URLs valid for 300 seconds. The download
  filename is sanitized before it is put in `Content-Disposition`.
- `uploads.delete_after` is set when an upload is created and the worker
  enforces retention. Terminal order paths are covered by the retention
  job rather than by deleting on one path only.
- `S3Storage.health()` creates a missing bucket, but does not make it
  public.

### Authorization

- Object-level authorization lives in services. Cross-tenant access
  returns 404 rather than 403, so the answer does not confirm that an
  object exists.
- API tests cover allowed and forbidden actors for orders, uploads,
  quality reports, vendor queue actions, admin shop decisions and
  customer order subscriptions.
- The WebSocket channel is derived on the server: a vendor socket is the
  shop that owns the account; a customer socket is that customer's order.

### Money and webhooks

- Prices are integer paise, computed only by `domain/pricing.py`, and the
  database has a `CHECK` constraint for the price formula.
- The fake and real gateways sign webhooks. The handler verifies on the
  raw body with a constant-time comparison, deduplicates by event id,
  checks amount and currency, commits the event and its effect in one
  transaction, and returns 5xx on transient failure so the provider
  retries.
- Late payments on expired orders are refunded.

### Input limits and abuse

- Request bodies are capped at the upload limit plus a small envelope;
  Caddy caps the forwarded body at 54 MB, above the application's 51 MiB
  cap and the 50 MB user limit.
- Uploads are limited to 300 pages, known file kinds, and are converted
  in the worker rather than in the request path.
- Rate limits are per account: uploads 10/min, order creation 20/min,
  shop search 30/min, vendor queue reads 60/min, vendor actions 60/min,
  reorder 10/min and wait estimates 60/min.
- Pickup codes allow five wrong attempts per order, then the order is
  rate limited. Codes are six digits and are checked by the service.

### Secrets and configuration

- `.env` is ignored. `.env.example` and `.env.prod.example` contain
  placeholders only. Development secrets are generated by
  `infra/scripts/generate-dev-secrets.sh`.
- CI uses obvious throwaway values, annotated as such, for variables the
  application refuses to start without. They are not deployment secrets.
- Production logs do not include PDF content, filenames beyond the
  minimum, tokens or storage keys. The console email sender used on a
  local machine writes the whole message, including the verification
  link, to the log; it refuses to start in production, and its output is
  a local artefact.

## Residual risks and follow-ups

1. **Single-instance state.** The rate limiter and the WebSocket hub are
   in-process. A second API instance would need a shared transport. This
   is documented in ADR 008 and ADR 034 and is a deployment constraint,
   not a hidden bug.
2. **Provider allowances in the CSP.** `'unsafe-inline'` for styles and
   `'unsafe-eval'` for the fraud widget are required by the identity
   provider. Removing them would break sign-up; the Caddyfile explains
   each one. Revisit when the provider stops requiring them.
3. **Free geocoder privacy.** A shop owner's typed address is sent to the
   configured geocoder. The default is OpenStreetMap's public service,
   and the setting can be pointed at a self-hosted instance or turned
   off. See ADR 031.
4. **Test-mode payments.** Razorpay runs in test mode; no real money
   moves. A production launch needs live keys, a webhook secret in the
   instance environment, and a fresh review of the live gateway path.

No SAST tool is wired in beyond Ruff and mypy. Bandit or Semgrep would be
a reasonable next step, but neither is a substitute for the tests around
money, authorization and the webhook.
