# ADR 015: A database browser in the local stack

Date: 2026-10-19
Status: Accepted
Requirement: Deployability, "local stack with one command" (PRD section 8)

## Context

The database is PostgreSQL with PostGIS, running in the `db` container
of the Compose stack. Reading it is a daily need: checking that a seeded
row looks right, confirming that an order moved from `PAID` to `READY`,
and finding out what a failed test actually wrote.

`psql` answers that, but it answers it in a terminal, in raw tuples,
with no schema to click through. A reviewer who opens the repository
wants the same thing MySQL Workbench or phpMyAdmin gives: a tree of
tables on the left, rows on the right.

The project also has rules that shape any answer. A secret never
belongs in a file in the repository. A development tool never belongs in
the production stack. And CI pulls only what CI needs, because every
extra image in a pipeline is time somebody waits for.

## Decision

Run pgAdmin as a service in `docker-compose.yml`, on port 5050, behind
a Compose profile called `tools`.

- The `spn (local)` server is pre-defined in `infra/pgadmin/servers.json`,
  so the connection is already there when the UI opens.
- The database password reaches pgAdmin through the environment
  (`SPN_DB_PASSWORD`, taken from the same `POSTGRES_PASSWORD` the
  database itself uses) and is read at connect time by pgAdmin's
  `PasswordExecCommand`. It is never typed, never stored by pgAdmin, and
  never written into the repository.
- `make up` and `make reset` enable the profile, so the browser comes up
  with the rest of the stack. `make down` enables it too, so the
  container does not outlive the stack.
- CI runs `docker compose up` without the profile, so pgAdmin is never
  pulled or started there.
- `docker-compose.prod.yml` does not mention it at all. A production
  deployment has no database browser, because a deployment that can
  rewrite the database is a deployment with a much larger blast radius.

## Alternatives considered

1. **A desktop client (DBeaver, TablePlus, Postico) on the host.**
   Rejected: it is the nicest to use, but it cannot be handed to a
   reviewer. Nobody else can see the data the way the project documents
   it, and the connection details live on one person's machine.
2. **Adminer, the single-container phpMyAdmin-alike.** Rejected: it is
   smaller and lighter than pgAdmin, and it does exactly the table
   browsing that is needed. pgAdmin was preferred because it is the
   reference Postgres tool, it ships the query tool, the ERD view and
   the backup tools that a Postgres project ends up wanting, and it is
   the tool an interviewer is most likely to recognise.
3. **An admin panel in the application itself.** Rejected: an admin UI
   is explicitly out of scope in `AGENTS.md`, and a hand-written one
   would be a second thing to keep correct and secure, next to the
   one tool that already does the job.

## Consequences

- One more image in the local stack, about 500 MB, pulled once. It is
  the price of a browser that works the same on any machine.
- The pgAdmin account is created on first launch, so changing
  `PGADMIN_PASSWORD` later needs the volume removed. This is documented
  in the README rather than worked around.
- The pre-defined server connection is loaded when the container's
  configuration is first created, which is how pgAdmin imports a server
  list. From then on the connection is an ordinary pgAdmin server that
  can be renamed, shared or edited in the UI.
- The browser shows the database as it really is, including the tables
  the tests wrote. That is the point.

## Revisit trigger

If the local stack grows enough that pulling a 500 MB image for a
development convenience is no longer acceptable, or if the project
decides to support a database other than PostgreSQL.
