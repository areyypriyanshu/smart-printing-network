#!/usr/bin/env bash
# Prove that a backup can be restored.
#
# A backup is only real once it has been restored. This takes the newest
# dump, restores it into a scratch database that is thrown away
# afterwards, and checks that the schema and the data came back. It
# never touches the live database.
#
# Usage: infra/scripts/restore-drill.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
BACKUP_DIR="${BACKUP_DIR:-${REPO_ROOT}/backups}"
SCRATCH_DB="${SCRATCH_DB:-spn_restore_drill}"

POSTGRES_USER="${POSTGRES_USER:-spn}"
POSTGRES_DB="${POSTGRES_DB:-spn}"

cd "${REPO_ROOT}"

db() {
	docker compose -f "${REPO_ROOT}/${COMPOSE_FILE}" exec -T db "$@"
}

cleanup() {
	echo "drill: dropping the scratch database"
	db dropdb -U "${POSTGRES_USER}" --if-exists "${SCRATCH_DB}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

NEWEST="$(find "${BACKUP_DIR}" -name 'spn-*.dump.gz' -type f | sort | tail -1)"
if [ -z "${NEWEST}" ]; then
	echo "drill: no backup found in ${BACKUP_DIR}. Run infra/scripts/backup.sh first." >&2
	exit 1
fi
echo "drill: using $(basename "${NEWEST}")"

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"; cleanup' EXIT
gzip -dc "${NEWEST}" > "${WORK}/restore.dump"

echo "drill: restoring into ${SCRATCH_DB}"
db dropdb -U "${POSTGRES_USER}" --if-exists "${SCRATCH_DB}" >/dev/null 2>&1 || true
db createdb -U "${POSTGRES_USER}" "${SCRATCH_DB}"
db pg_restore -U "${POSTGRES_USER}" -d "${SCRATCH_DB}" --no-owner --no-privileges < "${WORK}/restore.dump"

echo "drill: checking the restored schema"
TABLES="$(db psql -U "${POSTGRES_USER}" -d "${SCRATCH_DB}" -tAc \
	"SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';")"
echo "drill: ${TABLES} tables restored"
if [ "${TABLES}" -lt 8 ]; then
	echo "drill: expected the full schema, only found ${TABLES} tables" >&2
	exit 1
fi

for table in users shops orders payments order_events uploads; do
	COUNT="$(db psql -U "${POSTGRES_USER}" -d "${SCRATCH_DB}" -tAc "SELECT count(*) FROM ${table};")"
	echo "drill: ${table} has ${COUNT} rows"
done

echo "drill: checking the price invariant survived the restore"
BROKEN="$(db psql -U "${POSTGRES_USER}" -d "${SCRATCH_DB}" -tAc \
	"SELECT count(*) FROM orders WHERE price_paise <> GREATEST(page_count * copies * rate_paise, min_order_paise);")"
if [ "${BROKEN}" != "0" ]; then
	echo "drill: ${BROKEN} orders break the price formula in the restored copy" >&2
	exit 1
fi
echo "drill: every restored order still satisfies the price formula"

echo "drill: PASSED. The backup restores into a working database."
