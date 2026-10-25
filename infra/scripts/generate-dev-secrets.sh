#!/usr/bin/env bash
# Fill in the secrets a local checkout needs, and only if they are still the
# placeholders that ship in .env.example.
#
# The local stack is bound to loopback, but the values that ship in the
# template are public: anybody who has read the repository knows them. So a
# fresh checkout gets generated ones instead. A value the developer has
# already changed is left alone.
#
# A service whose password lives in a volume keeps the password it was
# created with. The database, the object store and the database browser all
# store their credentials that way, so changing the password in .env under
# a volume that already exists would lock the developer out of their own
# database. Those are left alone when the volume is there.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"
PROJECT="${SPN_COMPOSE_PROJECT:-spn}"

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

# Whether the volume a service keeps its state in is already there.
volume_exists() {
	if ! command -v docker >/dev/null 2>&1; then
		return 1
	fi
	docker volume ls --quiet --filter "name=^${1}$" 2>/dev/null | grep -q .
}

# The application secrets are not in a volume, so they are always the
# operator's to change. A public JWT secret means anybody can mint an
# access token for the local instance.
replace_placeholder JWT_SECRET "local-dev-placeholder-change-me-0123456789abcdef"

# The service credentials are published in the template as well, and they
# are only used when the volume is created. A volume that is already there
# keeps the password it was created with.
if volume_exists "${PROJECT}_postgres_data"; then
	echo "gen-secrets: the database volume is there, leaving its password alone"
else
	replace_placeholder POSTGRES_PASSWORD "spn"
	# DATABASE_URL carries the database password, so it has to follow it.
	if grep -qE '^POSTGRES_PASSWORD=' "${ENV_FILE}"; then
		password="$(grep -E '^POSTGRES_PASSWORD=' "${ENV_FILE}" | head -1 | cut -d= -f2-)"
		if grep -qE '^DATABASE_URL=' "${ENV_FILE}"; then
			sed -i.bak "s|^DATABASE_URL=.*|DATABASE_URL=postgresql+psycopg://spn:${password}@db:5432/spn|" \
				"${ENV_FILE}"
			rm -f "${ENV_FILE}.bak"
		fi
	fi
fi

if volume_exists "${PROJECT}_minio_data"; then
	echo "gen-secrets: the object store volume is there, leaving its password alone"
else
	replace_placeholder S3_SECRET_KEY "spn-local-secret"
fi

if volume_exists "${PROJECT}_pgadmin_data"; then
	echo "gen-secrets: the database browser volume is there, leaving its password alone"
else
	replace_placeholder PGADMIN_PASSWORD "spn"
fi

exit 0
