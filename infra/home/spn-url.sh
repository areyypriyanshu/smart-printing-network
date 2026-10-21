#!/usr/bin/env bash
#
# The public address of the deployment, and the application told about it.
#
# A quick tunnel is given a hostname at random, and a different one every
# time it starts. The application has to be told the new one, because the
# email verification link is built from APP_BASE_URL and a link to the
# old hostname leads nowhere.
#
# This script reads the hostname out of the tunnel's log, writes it into
# the instance's .env, and restarts the two services that read it.
#
# Usage:
#   infra/home/spn-url.sh             # print the address
#   infra/home/spn-url.sh --sync      # print it, write it into .env, restart
#   infra/home/spn-url.sh --wait 90   # wait up to 90 seconds for a tunnel
#
# It is safe to run it when the tunnel is not up: it prints nothing and
# changes nothing.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"
COMPOSE=(docker compose -f "${REPO_ROOT}/docker-compose.prod.yml" -f "${REPO_ROOT}/docker-compose.home.yml")
TUNNEL_CONTAINER="${SPN_TUNNEL_CONTAINER:-spn-home-tunnel-1}"

SYNC=0
WAIT_SECONDS=0
while [ $# -gt 0 ]; do
    case "$1" in
        --sync) SYNC=1 ;;
        --wait)
            shift
            WAIT_SECONDS="${1:-90}"
            ;;
        --wait=*) WAIT_SECONDS="${1#--wait=}" ;;
        *) echo "usage: spn-url.sh [--sync] [--wait SECONDS]" >&2; exit 2 ;;
    esac
    shift
done

# The hostname Cloudflare gave the tunnel. It is in the tunnel's log,
# when the tunnel starts. A restarted container keeps its log, so the
# log holds every hostname it has ever had, and the current one is the
# LAST of them. Taking the first would give the address of a tunnel
# that no longer exists, and every request to it comes back as a 530.
read_url() {
    docker logs "${TUNNEL_CONTAINER}" 2>&1 \
        | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' \
        | tail -1
}

URL=""
deadline=$(( $(date +%s) + WAIT_SECONDS ))
while true; do
    # The address is read again on every pass, and the request is made
    # to THAT one. A restarted container's log holds the old hostname
    # until the new one is written, so a script that reads the address
    # once and then waits would sit there waiting for a tunnel that no
    # longer exists.
    candidate="$(read_url || true)"
    if [ -n "$candidate" ]; then
        if [ "$WAIT_SECONDS" -eq 0 ]; then
            URL="$candidate"
            break
        fi
        # The hostname appears in the log a moment before the tunnel's
        # connection to the edge is registered, and a request in that
        # window comes back as a 502 or a 530. Wait until the site
        # answers, so that whoever runs this script gets an address
        # that works.
        code="$(curl -sS -m 10 -o /dev/null -w '%{http_code}' "${candidate}/readyz" 2>/dev/null || echo 000)"
        if [ "$code" = "200" ]; then
            URL="$candidate"
            break
        fi
    fi
    if [ "$(date +%s)" -ge "$deadline" ]; then
        break
    fi
    sleep 3
done

if [ -z "$URL" ]; then
    echo "spn-url: the tunnel has no working address yet" >&2
    exit 1
fi

echo "$URL"

if [ "$SYNC" -eq 1 ]; then
    # The application is told the new address. A named tunnel has a
    # fixed hostname, so its .env already says the right thing and
    # nothing is written.
    if grep -q "^APP_BASE_URL=" "$ENV_FILE"; then
        current="$(grep '^APP_BASE_URL=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
        if [ "$current" != "$URL" ]; then
            sed -i "s|^APP_BASE_URL=.*|APP_BASE_URL=${URL}|" "$ENV_FILE"
            echo "spn-url: the application was told the new address" >&2
            "${COMPOSE[@]}" up -d api worker >/dev/null
            # The API and the worker are restarting, and the edge
            # answers with a 502 while they are down. Wait for the
            # site to come back, so that the address this script
            # prints is one that works.
            deadline=$(( $(date +%s) + 60 ))
            while true; do
                code="$(curl -sS -m 10 -o /dev/null -w '%{http_code}' "${URL}/readyz" 2>/dev/null || echo 000)"
                if [ "$code" = "200" ]; then
                    break
                fi
                if [ "$(date +%s)" -ge "$deadline" ]; then
                    echo "spn-url: the site did not come back (last answer ${code})" >&2
                    exit 1
                fi
                sleep 3
            done
        fi
    fi
fi
