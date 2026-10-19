# ADR 011: Community-built MinIO image for local object storage

Date: 2026-10-19
Status: Accepted
Requirement: Sprint 0 foundation (IMPLEMENTATION_PLAN), FR-4 storage groundwork

## Context

Local development and CI need S3-compatible object storage for PDF uploads, presigned URLs and storage integration tests (TECH_STACK environment table). The plan assumed the official `minio/minio` Docker image.

In October 2025 MinIO made the community edition a source-only distribution. The maintainers stopped publishing prebuilt images: the last official image predates the security fix released as `RELEASE.2025-10-15T17-29-55Z` (privilege escalation via session policy bypass in service accounts and STS). The official Docker Hub repository is no longer reachable and quay.io serves no image for the fixed release. There is no official, patched MinIO image to pin.

## Decision

Use the community-built image `coollabsio/minio:RELEASE.2025-10-15T17-29-55Z` in `docker-compose.yml` for local development only.

- Built transparently from the official MinIO source at that release tag; the bundled `mc` client is minisign-verified against MinIO's public key during the build.
- Multi-arch (amd64, arm64).
- Pinned tag; never used in production. Production uses S3 via the storage gateway interface.

## Alternatives considered

1. Pin the last official image `RELEASE.2025-09-07T16-13-09Z`. Rejected: knowingly ships a privilege-escalation CVE and will never receive updates.
2. Build MinIO from source in our own Dockerfile. Rejected for now: multi-minute first build, larger image and extra CI complexity, for a local-only dependency. Reconsider if trust in the community image is lost.
3. Switch the local store to another S3-compatible project (for example Garage). Deferred: larger documentation and tooling churn; the S3 API surface our code uses is small and well covered by MinIO.

## Consequences

- boto3-based storage code is identical between local (MinIO) and production (S3); the gateway interface is unaffected.
- We accept a third-party build as a controlled supply-chain risk: pinned tag, used only for local development, no customer data.
- Community MinIO receives bug and CVE fixes only; no new features upstream. The local storage choice may need revisiting if that maintenance stops.

## Revisit trigger

When the S3Storage gateway is implemented (Sprint 2), re-verify the healthcheck and S3 compatibility against the pinned image; if the community image is no longer maintained, or an official MinIO distribution returns, replace the image and update this ADR.
