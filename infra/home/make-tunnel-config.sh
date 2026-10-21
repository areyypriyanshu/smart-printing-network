#!/usr/bin/env bash
#
# Write the Cloudflare Tunnel configuration for this box.
#
# The tunnel is a locally managed one: it has a credentials file on the
# machine, and it reads its own ingress rules from a configuration file
# rather than from the Cloudflare dashboard. Both the credentials and
# the configuration are specific to this deployment, so neither is in
# the repository.
#
# It writes two files into the output directory:
#
#   config.yml          the tunnel, the credentials path and the ingress
#   creds/<tunnel-id>.json  the tunnel credentials, copied out of ~/.cloudflared
#
# The credentials are copied rather than mounted from ~/.cloudflared on
# purpose: that directory also holds cert.pem, the account certificate,
# which can create tunnels and DNS records for every zone in the
# account. The tunnel needs one file, not that.
#
# Usage: infra/home/make-tunnel-config.sh <tunnel-id> <hostname> [output-dir]

set -euo pipefail

TUNNEL_ID="${1:?usage: make-tunnel-config.sh <tunnel-id> <hostname> [output-dir]}"
HOSTNAME_REQUIRED="${2:?usage: make-tunnel-config.sh <tunnel-id> <hostname> [output-dir]}"
OUT_DIR="${3:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/.tunnel}"

CREDENTIALS_DIR="${CREDENTIALS_DIR:-${HOME}/.cloudflared}"
SOURCE_CREDENTIALS="${CREDENTIALS_DIR}/${TUNNEL_ID}.json"

if [ ! -f "${SOURCE_CREDENTIALS}" ]; then
    echo "error: no tunnel credentials at ${SOURCE_CREDENTIALS}" >&2
    echo "       create the tunnel first: cloudflared tunnel create <name>" >&2
    exit 1
fi

mkdir -p "${OUT_DIR}"
chmod 700 "${OUT_DIR}"

# The credentials are a secret. Only the account that created them may
# read them, and the container that runs the tunnel runs as that same
# account.
#
# They go in a subdirectory, because cloudflared looks for a tunnel
# credentials file directly in its configuration directory. One there
# makes it run that tunnel, whatever it was asked to do, and the
# hostname it prints is then not the hostname the edge routes.
mkdir -p "${OUT_DIR}/creds"
chmod 700 "${OUT_DIR}/creds"
cp "${SOURCE_CREDENTIALS}" "${OUT_DIR}/creds/${TUNNEL_ID}.json"
chmod 400 "${OUT_DIR}/creds/${TUNNEL_ID}.json"

cat > "${OUT_DIR}/config.yml" <<EOF
# The Cloudflare Tunnel for this box.
#
# The tunnel makes an outbound connection to Cloudflare, so the router
# needs no port forwarding and the house needs no public address.
#
# The origin is Caddy over the Docker network, by its service name.
# Caddy issues that certificate from its own authority (SPN_TLS is
# "internal"), so the tunnel is told not to verify it, and to use the
# public hostname as the server name: Caddy serves the site under that
# name only, and a handshake for "caddy" would match no site at all.
tunnel: ${TUNNEL_ID}
credentials-file: /etc/cloudflared/creds/${TUNNEL_ID}.json

ingress:
  - hostname: ${HOSTNAME_REQUIRED}
    service: https://caddy:443
    originRequest:
      noTLSVerify: true
      originServerName: ${HOSTNAME_REQUIRED}
  - service: http_status:404
EOF
chmod 400 "${OUT_DIR}/config.yml"

echo "tunnel: wrote ${OUT_DIR}/config.yml for ${HOSTNAME_REQUIRED}"
echo "tunnel: the credentials are in ${OUT_DIR}/creds/${TUNNEL_ID}.json, readable by uid $(id -u) only"
