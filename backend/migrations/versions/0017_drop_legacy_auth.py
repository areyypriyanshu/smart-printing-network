"""Remove the pre-Clerk local auth schema after the rollback window.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-04

The compatibility release (98959fe) removed the ORM mappings for
`users.password_hash`, `users.has_password`, `refresh_tokens` and
`email_verification_tokens` but kept the physical schema for rollback
to the previous image. That window is now closed: the compatibility
image is deployed, the live inventory has been taken, and Clerk is the
sole sign-in path.

This contraction drops:

- `email_verification_tokens` (0009) - verification is proven by Clerk;
  `users.email_verified` is kept because the services still enforce it.
- `refresh_tokens` (0002) - local sessions; Clerk issues sessions now.
- `users.password_hash` (0002) and `users.has_password` (0011) - local
  password machinery.

The upgrade is atomic: before dropping anything the migration copies
the legacy rows into transaction-local `spn_archive_*` tables, drops
the live objects, and drops the archives, all in one transaction, so a
failure leaves the schema untouched. Downgrade recreates the tables and
columns so the previous image can start again, with sentinel hashes in
place of the original passwords (the rollback window is closed and
every live user already has a `clerk_user_id`, so nobody needs the
original hashes back). If a legacy table is already gone (for example
a locally recreated dev database), the copy insert selects from nothing
and the drop path still works.

Users with no archived hash get a sentinel hash of nothing on
downgrade, per the 0014 policy: it restores `NOT NULL` without giving
anyone a usable password.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          CREATE TABLE spn_archive_users_password_hash (
            user_id uuid NOT NULL,
            password_hash text NOT NULL
          );
          CREATE TABLE spn_archive_refresh_tokens (
            id uuid NOT NULL,
            user_id uuid NOT NULL,
            family_id uuid NOT NULL,
            token_hash char(64) NOT NULL,
            expires_at timestamptz NOT NULL,
            revoked_at timestamptz,
            created_at timestamptz NOT NULL
          );
          CREATE TABLE spn_archive_email_verification_tokens (
            id uuid NOT NULL,
            user_id uuid NOT NULL,
            token_hash char(64) NOT NULL,
            expires_at timestamptz NOT NULL,
            used_at timestamptz,
            created_at timestamptz NOT NULL
          );
          IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'users'
              AND column_name = 'password_hash'
          ) THEN
            INSERT INTO spn_archive_users_password_hash (user_id, password_hash)
              SELECT id, password_hash FROM users WHERE password_hash IS NOT NULL;
          END IF;
          IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'refresh_tokens'
          ) THEN
            INSERT INTO spn_archive_refresh_tokens
              (id, user_id, family_id, token_hash, expires_at, revoked_at, created_at)
              SELECT id, user_id, family_id, token_hash, expires_at, revoked_at, created_at
                FROM refresh_tokens;
          END IF;
          IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'email_verification_tokens'
          ) THEN
            INSERT INTO spn_archive_email_verification_tokens
              (id, user_id, token_hash, expires_at, used_at, created_at)
              SELECT id, user_id, token_hash, expires_at, used_at, created_at
                FROM email_verification_tokens;
          END IF;
          DROP TABLE IF EXISTS email_verification_tokens;
          DROP TABLE IF EXISTS refresh_tokens;
          ALTER TABLE users DROP COLUMN IF EXISTS password_hash;
          ALTER TABLE users DROP COLUMN IF EXISTS has_password;
          DROP TABLE spn_archive_users_password_hash,
                     spn_archive_refresh_tokens,
                     spn_archive_email_verification_tokens;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          CREATE TABLE spn_archive_users_password_hash (
            user_id uuid NOT NULL,
            password_hash text NOT NULL
          );
          CREATE TABLE spn_archive_refresh_tokens (
            id uuid NOT NULL,
            user_id uuid NOT NULL,
            family_id uuid NOT NULL,
            token_hash char(64) NOT NULL,
            expires_at timestamptz NOT NULL,
            revoked_at timestamptz,
            created_at timestamptz NOT NULL
          );
          CREATE TABLE spn_archive_email_verification_tokens (
            id uuid NOT NULL,
            user_id uuid NOT NULL,
            token_hash char(64) NOT NULL,
            expires_at timestamptz NOT NULL,
            used_at timestamptz,
            created_at timestamptz NOT NULL
          );
          IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'users'
              AND column_name = 'password_hash'
          ) THEN
            INSERT INTO spn_archive_users_password_hash (user_id, password_hash)
              SELECT id, password_hash FROM users WHERE password_hash IS NOT NULL;
          END IF;
          IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'refresh_tokens'
          ) THEN
            INSERT INTO spn_archive_refresh_tokens
              (id, user_id, family_id, token_hash, expires_at, revoked_at, created_at)
              SELECT id, user_id, family_id, token_hash, expires_at, revoked_at, created_at
                FROM refresh_tokens;
          END IF;
          IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'email_verification_tokens'
          ) THEN
            INSERT INTO spn_archive_email_verification_tokens
              (id, user_id, token_hash, expires_at, used_at, created_at)
              SELECT id, user_id, token_hash, expires_at, used_at, created_at
                FROM email_verification_tokens;
          END IF;
          DROP TABLE IF EXISTS email_verification_tokens;
          DROP TABLE IF EXISTS refresh_tokens;
          ALTER TABLE users DROP COLUMN IF EXISTS password_hash;
          ALTER TABLE users DROP COLUMN IF EXISTS has_password;
          ALTER TABLE users ADD COLUMN password_hash text;
          ALTER TABLE users ADD COLUMN has_password boolean;
          UPDATE users
             SET has_password = true
           WHERE has_password IS NULL;
          ALTER TABLE users ALTER COLUMN has_password SET NOT NULL;
          ALTER TABLE users ALTER COLUMN has_password SET DEFAULT true;
          CREATE TABLE refresh_tokens (
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL,
            family_id uuid NOT NULL,
            token_hash char(64) NOT NULL,
            expires_at timestamptz NOT NULL,
            revoked_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT refresh_tokens_pkey PRIMARY KEY (id),
            CONSTRAINT refresh_tokens_token_hash_key UNIQUE (token_hash),
            CONSTRAINT refresh_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id)
          );
          CREATE INDEX refresh_tokens_user_idx ON refresh_tokens (user_id);
          CREATE INDEX refresh_tokens_family_idx ON refresh_tokens (family_id);
          CREATE TABLE email_verification_tokens (
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL,
            token_hash char(64) NOT NULL,
            expires_at timestamptz NOT NULL,
            used_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT email_verification_tokens_pkey PRIMARY KEY (id),
            CONSTRAINT email_verification_tokens_token_hash_key UNIQUE (token_hash),
            CONSTRAINT email_verification_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id)
          );
          CREATE INDEX email_verification_tokens_user_idx
            ON email_verification_tokens (user_id);
          CREATE INDEX email_verification_tokens_expiry_idx
            ON email_verification_tokens (expires_at);
          INSERT INTO refresh_tokens
            (id, user_id, family_id, token_hash, expires_at, revoked_at, created_at)
            SELECT id, user_id, family_id, token_hash, expires_at, revoked_at, created_at
              FROM spn_archive_refresh_tokens;
          INSERT INTO email_verification_tokens
            (id, user_id, token_hash, expires_at, used_at, created_at)
            SELECT id, user_id, token_hash, expires_at, used_at, created_at
              FROM spn_archive_email_verification_tokens;
          UPDATE users u
             SET password_hash = a.password_hash
            FROM spn_archive_users_password_hash a
           WHERE u.id = a.user_id;
          UPDATE users
             SET password_hash = '$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHRzb21lc2FsdA$'
           WHERE password_hash IS NULL;
          ALTER TABLE users ALTER COLUMN password_hash SET NOT NULL;
          DROP TABLE spn_archive_users_password_hash,
                     spn_archive_refresh_tokens,
                     spn_archive_email_verification_tokens;
        END $$;
        """
    )
