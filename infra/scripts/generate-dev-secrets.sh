#!/usr/bin/env bash
# Fill in the secrets a local checkout needs, and only if they are still the
# placeholders that ship in .env.example.
#
# The local stack is bound to loopback, but the values that ship in the
# template are public: anybody who has read the repository knows them. So a
# fresh checkout gets generated ones instead. A value the developer has
# already changed is left alone.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

if [ ! -f "${ENV_FILE}" ]; then
	echo "gen-secrets: no .env to fill in" >&2
	exit 0
fi

random_secret() {
	# A URL-safe alphabet, because the database password ends up inside a
	# connection URL and a '+' or a '/' would have to be escaped there.
	if command -v openssl >/dev/null 2>&1; then
		openssl rand -base64 48 | tr '+/' '-_' | tr -d '=\n'
	else
		head -c 48 /dev/urandom | base64 | tr '+/' '-_' | tr -d '=\n'
	fi
}

# replace KEY when its current value still holds the placeholder.
replace_placeholder() {
	key="$1"
	placeholder="$2"
	current="$(grep -E "^${key}=" "${ENV_FILE}" | head -1 | cut -d= -f2- || true)"
	if [ -z "${current}" ] || [ "${current}" = "${placeholder}" ]; then
		secret="$(random_secret)"
		if grep -qE "^${key}=" "${ENV_FILE}"; then
			sed -i.bak "s|^${key}=.*|${key}=${secret}|" "${ENV_FILE}"
		else
			printf '\n%s=%s\n' "${key}" "${secret}" >>"${ENV_FILE}"
		fi
		rm -f "${ENV_FILE}.bak"
		echo "gen-secrets: set ${key}"
	fi
}

replace_placeholder JWT_SECRET "local-dev-placeholder-change-me-0123456789abcdef"
replace_placeholder FAKE_WEBHOOK_SECRET "local-dev-placeholder-change-me-too-0123456789abcdef"

# The database, the object store and the database browser are bound to
# loopback, but their credentials are still published, so they get generated
# ones too.
replace_placeholder POSTGRES_PASSWORD "spn"
replace_placeholder S3_SECRET_KEY "spn-local-secret"
replace_placeholder PGADMIN_PASSWORD "spn"

# DATABASE_URL carries the database password, so it has to follow it.
if grep -qE '^POSTGRES_PASSWORD=' "${ENV_FILE}"; then
	password="$(grep -E '^POSTGRES_PASSWORD=' "${ENV_FILE}" | head -1 | cut -d= -f2-)"
	if grep -qE '^DATABASE_URL=' "${ENV_FILE}"; then
		sed -i.bak "s|^DATABASE_URL=.*|DATABASE_URL=postgresql+psycopg://spn:${password}@db:5432/spn|" \
			"${ENV_FILE}"
		rm -f "${ENV_FILE}.bak"
	fi
fi

exit 0
