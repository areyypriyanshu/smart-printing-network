#!/usr/bin/env bash
# Take a database backup and keep it off the instance.
#
# A backup that only exists on the machine it was taken from is not a
# backup. This writes a compressed dump to BACKUP_DIR and, when the
# upload settings are present, copies it to the backup bucket.
#
# Usage: infra/scripts/backup.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
BACKUP_DIR="${BACKUP_DIR:-${REPO_ROOT}/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"

POSTGRES_USER="${POSTGRES_USER:-spn}"
POSTGRES_DB="${POSTGRES_DB:-spn}"

mkdir -p "${BACKUP_DIR}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="${BACKUP_DIR}/spn-${STAMP}.dump"

echo "backup: dumping ${POSTGRES_DB} to ${DEST}"
docker compose -f "${REPO_ROOT}/${COMPOSE_FILE}" exec -T db \
	pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --format=custom > "${DEST}"

gzip -9 "${DEST}"
DEST="${DEST}.gz"

SIZE="$(du -h "${DEST}" | cut -f1)"
echo "backup: wrote ${DEST} (${SIZE})"

# Copy to the backup bucket when one is configured. A local run without
# bucket settings keeps the file on disk only, which is enough for the
# restore drill.
if [ -n "${BACKUP_BUCKET:-}" ] && [ -n "${AWS_ACCESS_KEY_ID:-}" ]; then
	echo "backup: uploading to s3://${BACKUP_BUCKET}/"
	aws s3 cp "${DEST}" "s3://${BACKUP_BUCKET}/spn-${STAMP}.dump.gz" \
		--endpoint-url "${S3_ENDPOINT_URL:-}" --storage-class STANDARD_IA
else
	echo "backup: no BACKUP_BUCKET configured, keeping the dump on disk only"
fi

# Keep the local copies for a month.
find "${BACKUP_DIR}" -name 'spn-*.dump.gz' -type f -mtime "+${RETENTION_DAYS}" -print -delete
echo "backup: done"
