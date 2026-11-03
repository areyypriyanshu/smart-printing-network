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

# A restarted container keeps its log. Read the recent startup window so
# an older hostname in the full log cannot win over the current tunnel.
read_url() {
    docker logs --tail 40 "${TUNNEL_CONTAINER}" 2>&1 \
        | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' \
        | tail -1
}

public_ready() {
    local code
    local hostname
    hostname="${1#https://}"
    # The generated hostname can be missing from this server's DNS cache
    # even after Cloudflare has published it. Connect through the base
    # domain's Cloudflare edge IP while retaining the generated hostname
    # for TLS SNI and HTTP routing.
    code="$(curl -sS -m 10 -o /dev/null -w '%{http_code}' \
        --connect-to "${hostname}:443:trycloudflare.com:443" \
        "${1}/readyz" 2>/dev/null || true)"
    [ "${code}" = "200" ]
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
        # Check the public edge without depending on local DNS for this
        # particular random hostname.
        if public_ready "${candidate}"; then
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
    CHANGED=0
    if grep -q "^APP_BASE_URL=" "$ENV_FILE"; then
        current="$(grep '^APP_BASE_URL=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
        if [ "$current" != "$URL" ]; then
            sed -i "s|^APP_BASE_URL=.*|APP_BASE_URL=${URL}|" "$ENV_FILE"
            echo "spn-url: the application was told the new address" >&2
            CHANGED=1
        fi
    fi
    # The identity provider checks the origin the session token was
    # asked for, so the address the browser uses has to be one the
    # application allows. The address changes when the tunnel starts,
    # so the list of allowed origins changes with it.
    if grep -q "^CLERK_ALLOWED_ORIGINS=" "$ENV_FILE"; then
        origins="$(grep '^CLERK_ALLOWED_ORIGINS=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
        case ",${origins}," in
            *",${URL},"*) ;;
            *)
                sed -i "s|^CLERK_ALLOWED_ORIGINS=.*|CLERK_ALLOWED_ORIGINS=${URL}|" "$ENV_FILE"
                echo "spn-url: the allowed origins were told the new address" >&2
                CHANGED=1
                ;;
        esac
    fi

    if [ "$CHANGED" -eq 1 ]; then
        "${COMPOSE[@]}" up -d api worker >/dev/null
        # The API and the worker are restarting, and the edge answers
        # with a 502 while they are down. Wait for the site to come
        # back, so that the address this script prints is one that
        # works.
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
