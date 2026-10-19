# ADR 008: Single instance with Docker Compose before managed AWS services

Date: 2026-10-19
Status: Accepted
Requirement: Phase 1 deploy and environments

## Context

The system has to run somewhere. The options range from a single server running Docker Compose to a managed Kubernetes cluster with RDS, ElastiCache, S3, ECS, Application Load Balancers and Terraform.

The project is built by one developer, and the portfolio goal is to be deployable and explainable. A complex cloud architecture is a thing that can break, costs real money, and takes more time to configure than to build the app itself. It also hides the details of how the pieces talk to each other behind managed services.

## Decision

Run the whole stack on a single AWS instance (Lightsail or EC2), orchestrated by Docker Compose, with Caddy terminating TLS and reverse-proxying the containers.

- The database is PostgreSQL running in a container, with nightly `pg_dump` to an S3 bucket and a restore drill script.
- The object storage is MinIO locally and S3 in production, accessed through the same boto3 storage adapter.
- The background worker is a second container running the same image as the API, using the same database.
- Caddy serves the built React SPA and reverse-proxies `/api` and the health checks. There is one origin, so there is no CORS and the refresh cookie is first-party.

## Alternatives considered

1. **Managed Kubernetes (EKS / GKE).** Rejected: massive complexity, high monthly cost, and no multi-instance scaling requirement. Kubernetes solves a scaling problem this project does not have.
2. **Platform as a Service (Render, Railway, Fly.io).** Rejected: hides the database extension setup (PostGIS) and the reverse proxy configuration (Caddy, TLS, security headers, CSP) behind a platform interface, which makes the deploy story less teachable and less portable.
3. **PaaS for the app plus RDS for the database.** Rejected: more expensive, two places to configure secrets, and a split network path. A single instance with a persistent volume is simpler and enough.

## Consequences

- The entire production stack is one `docker-compose.prod.yml` file and a Caddyfile. Anyone who can run Docker can run the production stack locally, exactly the way it runs in the cloud.
- Scaling is limited to the size of the single instance. That is an intentional ceiling: the project targets low to medium traffic, and scaling triggers are documented for when growth demands them.
- If the instance dies, the app is down until it restarts or is recreated from a backup. The nightly backup and the restore drill are what make that risk acceptable.
- The single-instance limit affects the in-memory rate limiter and the background jobs: jobs are safe because they use `SKIP LOCKED`, but the rate limiter counts per container. If a second API instance were added, rate limiting would have to move to Redis.

## Revisit trigger

When traffic exceeds a single instance's CPU or memory, or high availability (zero downtime deploys across instances) becomes a requirement.
