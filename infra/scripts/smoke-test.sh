#!/usr/bin/env bash
# End to end smoke test against a running deployment.
#
# Walks the whole order flow the way a person would: a customer uploads a
# PDF, sees a price, reserves the job, and the shop works the order from
# the queue to the handover against the pickup code. The customer pays in
# cash at the counter, so there is no payment provider to call. It checks
# the answer at every step, so it fails loudly rather than printing a
# summary that looks fine.
#
# Usage:
#   infra/scripts/smoke-test.sh                       # the local dev stack
#   BASE_URL=https://localhost infra/scripts/smoke-test.sh
#
# It needs the seeded demo accounts, so run `make seed` first. It signs
# in through the local way in, which is refused in production, so it
# cannot run against a deployment that has SPN_DEV_AUTH off.

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
API="${BASE_URL}/api/v1"
CUSTOMER_EMAIL="${CUSTOMER_EMAIL:-customer@example.com}"
VENDOR_EMAIL="${VENDOR_EMAIL:-vendor1@example.com}"

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

# A local run over HTTPS uses a certificate from Caddy's own authority.
# Point CURL_CA_BUNDLE at that certificate, or set SPN_INSECURE=1 to skip
# the check. The certificate can be fetched with:
#   docker compose -f docker-compose.prod.yml exec caddy \
#     wget -qO- http://localhost:2019/pki/ca/cert.crt > caddy-ca.crt
CURL_ARGS=()
if [ -n "${CURL_CA_BUNDLE:-}" ]; then
	CURL_ARGS+=(--cacert "${CURL_CA_BUNDLE}")
elif [ "${SPN_INSECURE:-0}" = "1" ]; then
	CURL_ARGS+=(--insecure)
fi

step() {
	printf '\n== %s\n' "$1"
}

fail() {
	echo "SMOKE TEST FAILED: $1" >&2
	exit 1
}

# A tiny but genuine one page PDF.
make_pdf() {
	python3 - "$1" <<'PY'
import sys
path = sys.argv[1]
objects = [
    b"<< /Type /Catalog /Pages 2 0 R >>",
    b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
    b"/Resources << /Font << /F1 5 0 R >> >> >>",
    None,
    b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
]
stream = b"BT /F1 18 Tf 72 700 Td (Smart Printing Network smoke test) Tj ET"
objects[3] = (
    b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
)
out = bytearray(b"%PDF-1.4\n")
offsets = []
for index, obj in enumerate(objects, 1):
    offsets.append(len(out))
    out += str(index).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
start = len(out)
out += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n0000000000 65535 f \n"
for offset in offsets:
    out += ("%010d 00000 n \n" % offset).encode()
out += (
    b"trailer\n<< /Size "
    + str(len(objects) + 1).encode()
    + b" /Root 1 0 R >>\nstartxref\n"
    + str(start).encode()
    + b"\n%%EOF\n"
)
open(path, "wb").write(bytes(out))
PY
}

login() {
	local email="$1"
	curl -sS "${CURL_ARGS[@]+"${CURL_ARGS[@]}"}" -X POST "${API}/auth/dev-session" -H 'Content-Type: application/json' \
		-d "{\"email\":\"${email}\"}" |
		python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])'
}

step "the service is up"
curl -sSf "${CURL_ARGS[@]+"${CURL_ARGS[@]}"}" "${BASE_URL}/readyz" > /dev/null || fail "the service is not ready"
echo "ready"

step "the customer signs in"
CUSTOMER_TOKEN="$(login "${CUSTOMER_EMAIL}")" || fail "the customer could not sign in"
echo "signed in as ${CUSTOMER_EMAIL}"

step "the customer uploads a PDF"
make_pdf "${WORK}/smoke.pdf"
UPLOAD="$(curl -sS "${CURL_ARGS[@]+"${CURL_ARGS[@]}"}" -X POST "${API}/uploads" -H "Authorization: Bearer ${CUSTOMER_TOKEN}" \
	-F "file=@${WORK}/smoke.pdf;type=application/pdf")"
UPLOAD_ID="$(printf '%s' "${UPLOAD}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')" ||
	fail "the upload was refused: ${UPLOAD}"
echo "uploaded ${UPLOAD_ID}"

step "the customer asks for the quality check"
QUALITY="$(curl -sS "${CURL_ARGS[@]+"${CURL_ARGS[@]}"}" -X POST "${API}/uploads/${UPLOAD_ID}/quality" \
	-H "Authorization: Bearer ${CUSTOMER_TOKEN}")" || fail "the quality check was refused: ${QUALITY}"
printf '%s' "${QUALITY}" | python3 -c '
import json,sys
body = json.load(sys.stdin)
status = body["status"]
if status not in ("PENDING", "RUNNING", "DONE"):
    raise SystemExit("the report should be waiting or done, it is " + status)
' || fail "the quality report is not in a sensible state: ${QUALITY}"
echo "the report is queued"

step "the worker finishes the quality check"
QUALITY_STATUS=""
for attempt in $(seq 1 30); do
	QUALITY="$(curl -sS "${CURL_ARGS[@]+"${CURL_ARGS[@]}"}" "${API}/uploads/${UPLOAD_ID}/quality" \
		-H "Authorization: Bearer ${CUSTOMER_TOKEN}")"
	QUALITY_STATUS="$(printf '%s' "${QUALITY}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')"
	[ "${QUALITY_STATUS}" != "PENDING" ] && [ "${QUALITY_STATUS}" != "RUNNING" ] && break
	sleep 1
done
[ "${QUALITY_STATUS}" = "DONE" ] || fail "the quality check should be DONE, it is ${QUALITY_STATUS}"
printf '%s' "${QUALITY}" | python3 -c '
import json,sys
body = json.load(sys.stdin)
if len(body["pages"]) != 1:
    raise SystemExit("the report should have one page")
if body["algorithm_version"] != "1":
    raise SystemExit("the report should say which algorithm made it")
' || fail "the quality report is not what it should be: ${QUALITY}"
echo "done, one page measured"

step "the warnings never block the order"
printf '%s' "${QUALITY}" | python3 -c '
import json,sys
body = json.load(sys.stdin)
flags = {flag for page in body["pages"] for flag in page["flags"]}
if flags - {"LOW_RESOLUTION", "VERY_LOW_RESOLUTION", "BLURRY"}:
    raise SystemExit(f"unexpected flags: {flags}")
' || fail "the report carried an unexpected flag"

step "the shop signs in and the customer can see it"
VENDOR_TOKEN="$(login "${VENDOR_EMAIL}")" || fail "the vendor could not sign in"
SHOP_ID="$(curl -sS "${CURL_ARGS[@]+"${CURL_ARGS[@]}"}" "${API}/vendor/shop" -H "Authorization: Bearer ${VENDOR_TOKEN}" |
	python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')" || fail "the vendor has no shop"
SHOPS="$(curl -sS "${CURL_ARGS[@]+"${CURL_ARGS[@]}"}" "${API}/shops" -H "Authorization: Bearer ${CUSTOMER_TOKEN}")"
printf '%s' "${SHOPS}" | python3 -c '
import json,sys
shop_id = sys.argv[1]
items = json.load(sys.stdin)["items"]
if not any(item["id"] == shop_id for item in items):
    raise SystemExit("the shop is not in the public list")
' "${SHOP_ID}" || fail "the shop is not in the public list"
QUOTE="$(curl -sS "${CURL_ARGS[@]+"${CURL_ARGS[@]}"}" -X POST "${API}/quotes" -H "Authorization: Bearer ${CUSTOMER_TOKEN}" \
	-H 'Content-Type: application/json' \
	-d "{\"upload_id\":\"${UPLOAD_ID}\",\"shop_id\":\"${SHOP_ID}\",\"paper_size\":\"A4\",\"color\":false,\"duplex\":false,\"copies\":2}")"
PRICE="$(printf '%s' "${QUOTE}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["price_paise"])')" ||
	fail "the quote was refused: ${QUOTE}"
echo "quoted ${PRICE} paise"

step "the customer reserves the order"
ORDER="$(curl -sS "${CURL_ARGS[@]+"${CURL_ARGS[@]}"}" -X POST "${API}/orders" -H "Authorization: Bearer ${CUSTOMER_TOKEN}" \
	-H "Idempotency-Key: smoke-$(date +%s)-$$" -H 'Content-Type: application/json' \
	-d "{\"upload_id\":\"${UPLOAD_ID}\",\"shop_id\":\"${SHOP_ID}\",\"paper_size\":\"A4\",\"color\":false,\"duplex\":false,\"copies\":2,\"expected_price_paise\":${PRICE}}")"
ORDER_ID="$(printf '%s' "${ORDER}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["order"]["id"])')" ||
	fail "the order was refused: ${ORDER}"
echo "order ${ORDER_ID}"

step "the order is reserved with a pickup code"
read -r STATUS CODE <<<"$(curl -sS "${CURL_ARGS[@]+"${CURL_ARGS[@]}"}" "${API}/orders/${ORDER_ID}" -H "Authorization: Bearer ${CUSTOMER_TOKEN}" |
	python3 -c 'import json,sys; d=json.load(sys.stdin)["order"]; print(d["status"], d["pickup_code"])')"
[ "${STATUS}" = "RESERVED" ] || fail "the order should be reserved, it is ${STATUS}"
[ -n "${CODE}" ] || fail "a reserved order must have a pickup code"
echo "reserved, pickup code ${CODE}"

step "the shop sees the order in the queue"
QUEUE="$(curl -sS "${CURL_ARGS[@]+"${CURL_ARGS[@]}"}" "${API}/vendor/queue" -H "Authorization: Bearer ${VENDOR_TOKEN}")"
printf '%s' "${QUEUE}" | python3 -c '
import json,sys
order_id = sys.argv[1]
items = json.load(sys.stdin)["items"]
if not any(item["id"] == order_id for item in items):
    raise SystemExit("the order is not in the queue")
' "${ORDER_ID}" || fail "the order is not in the vendor queue"
echo "the order is in the queue"

step "the shop accepts, prints and marks it ready"
for action in accept start ready; do
	curl -sSf "${CURL_ARGS[@]+"${CURL_ARGS[@]}"}" -X POST "${API}/vendor/orders/${ORDER_ID}/${action}" \
		-H "Authorization: Bearer ${VENDOR_TOKEN}" > /dev/null || fail "the ${action} was refused"
	echo "${action}"
done

step "the customer can download the file"
FILE="$(curl -sS "${CURL_ARGS[@]+"${CURL_ARGS[@]}"}" "${API}/orders/${ORDER_ID}/file" -H "Authorization: Bearer ${CUSTOMER_TOKEN}")"
printf '%s' "${FILE}" | python3 -c '
import json,sys
body = json.load(sys.stdin)
assert body["expires_in_seconds"] == 300, body
assert body["url"]
' || fail "the file link was refused: ${FILE}"
echo "a five minute link"

step "the wrong pickup code is refused"
WRONG="$(curl -sS "${CURL_ARGS[@]+"${CURL_ARGS[@]}"}" -o /dev/null -w '%{http_code}' -X POST "${API}/vendor/orders/${ORDER_ID}/collect" \
	-H "Authorization: Bearer ${VENDOR_TOKEN}" -H 'Content-Type: application/json' \
	-d '{"code":"000000"}')"
[ "${WRONG}" = "400" ] || fail "a wrong pickup code should be refused with 400, got ${WRONG}"
echo "refused"

step "the right pickup code completes the order"
COLLECTED="$(curl -sS "${CURL_ARGS[@]+"${CURL_ARGS[@]}"}" -X POST "${API}/vendor/orders/${ORDER_ID}/collect" \
	-H "Authorization: Bearer ${VENDOR_TOKEN}" -H 'Content-Type: application/json' \
	-d "{\"code\":\"${CODE}\"}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')"
[ "${COLLECTED}" = "COLLECTED" ] || fail "the order should be collected, it is ${COLLECTED}"
echo "collected"

step "the customer sees the finished order"
read -r FINAL PAID_AT <<<"$(curl -sS "${CURL_ARGS[@]+"${CURL_ARGS[@]}"}" "${API}/orders/${ORDER_ID}" -H "Authorization: Bearer ${CUSTOMER_TOKEN}" |
	python3 -c 'import json,sys; d=json.load(sys.stdin)["order"]; print(d["status"], d["paid_at"])')"
[ "${FINAL}" = "COLLECTED" ] || fail "the customer should see COLLECTED, they see ${FINAL}"
[ "${PAID_AT}" != "None" ] || fail "a collected cash order should record when it was paid"
echo "${FINAL}, paid at ${PAID_AT}"

printf '\nSMOKE TEST PASSED against %s\n' "${BASE_URL}"
