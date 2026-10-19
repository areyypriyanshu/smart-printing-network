# ADR 001: FastAPI over Node/Express

Date: 2026-10-19
Status: Accepted
Requirement: all Phase 1 backend work, TECH_STACK

## Context

The backend needs form-heavy HTTP endpoints, strict validation, an auto-generated OpenAPI contract for the typed frontend and Schemathesis, SQL access, and Phase 2 PDF and image analysis (PyMuPDF, OpenCV) in a worker. One developer builds and defends the whole system.

## Decision

Build the API with Python 3.12 and FastAPI, with Pydantic v2 for request and response validation.

## Alternatives considered

1. **Node/Express with TypeScript.** One language across the stack. Rejected: the Phase 2 PDF and image analysis that anchors the project lives in the Python ecosystem, so a Python service would appear anyway; a second service is worse than a second toolchain in one repo.
2. **Django with DRF.** Batteries included, admin out of the box. Rejected: the admin is explicitly out of scope, the ORM and settings model fit the domain less well, and the project wants a thin, explainable API layer.

## Consequences

- Two languages and toolchains (uv and npm) in one repository; the OpenAPI contract is the seam between them, and frontend types are generated from it.
- Auto-generated docs and an OpenAPI schema feed Schemathesis fuzzing and the frontend client for free.
- The Phase 2 worker runs PyMuPDF and OpenCV natively rather than through another process boundary.

## Revisit trigger

If the project adopts a single-language constraint, or the frontend needs server-rendered or BFF-only patterns that fight the API-first split.
