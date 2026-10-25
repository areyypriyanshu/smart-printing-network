# ADR 023: The deployment runs the commit it reviewed, in a mode it pins

Date: 2026-10-19
Status: Accepted; the payment-provider checks described here were removed with ADR 035, and the identity provider's checks took their place
Requirement: deployability (a project wide constraint)

## Context

The deployment is three files and a workflow: `docker-compose.prod.yml` for the topology, `infra/Caddyfile` for the edge, and `.github/workflows/deploy.yml` for the release. Each of them can decide something that the code does not, and each of them did.

The workflow built the API image and published it under the commit's name, but the compose file referred to the frontend under a mutable `:latest` tag that no workflow built. The browser therefore ran an image that was not the one the release had built, and nobody could say which one it was.

The workflow could be dispatched on any ref. The images were built from the dispatch's ref, so a dispatch on a branch deployed a branch, without anything having reviewed it as a release.

The production compose file read the application's mode from an untracked `.env` on the instance. Every production-only check was keyed on the exact string `production`: the placeholder JWT secret was refused, the fake payment provider was refused, the testing surface was refused, and the refresh cookie was marked Secure. A `.env` that said `prod`, or that had been edited by hand, turned all of them off at once, silently.

The local stack published the database, the object store, the API and the database browser on every interface, with the credentials that ship in `.env.example`.

The webhook key for the fake payment provider was a constant in the application package, and the public webhook route verified signatures with it.

## Decision

**What is deployed is what was reviewed, and what runs is what is configured.**

- The workflow builds both images from the same commit and publishes both under the commit's name. The deployment names both by that name, and the rollback remembers both.
- A dispatch on anything but `main` is refused by the workflow itself, and the checkout is pinned to the commit the images were built from.
- The production compose file pins `ENV: production`, `TESTING_ENDPOINTS_ENABLED: false` and the JWT secret for the API and the worker. A Compose `environment` entry overrides `env_file`, so the two cannot disagree, and the instance's file cannot loosen the mode.
- The application refuses to start with a mode that is not exactly `local`, `test` or `production`. A spelling that is nearly right is a mistake, not a mode.
- The fake payment provider is refused in production, and it takes an operator-supplied webhook key. There is no default, because a key in the repository is a key that everybody who has read the repository can use to mark an order paid.
- The local stack binds every published port to loopback, and `make up` generates the secrets the template ships with, so a fresh checkout does not run on a published value.
- The edge does not trust a forwarded address from the private ranges, and the application only believes the forwarded address from the proxy it is behind.

## Alternatives considered

1. **Keep the mutable tag and let `docker compose pull` find the current one.** Rejected: the pull decides what runs, and the decision is not in the release. A rollback would not roll back to a known image either.
2. **Trust the branch protection of `main` and let a dispatch choose the ref.** Rejected: branch protection says who may merge, not what may be deployed. The workflow checks the ref it is deploying.
3. **Keep the mode in the instance's `.env` and validate it at startup.** Rejected: the validation is the thing that failed. A mode that is not `production` disables every production-only check at once, and the failure is silent. Pinning it in the compose file means the instance cannot change it by accident.
4. **Keep the published local credentials, and rely on the local stack being on a developer's own machine.** Rejected: a laptop on a café network is a shared network. The ports are bound to loopback, so the stack is not reachable from it.
5. **Generate the local secrets by hand in the setup instructions.** Rejected: a step that is easy to skip is a step that is skipped. `make up` does it, and it leaves alone anything the developer has already changed.

## Consequences

- The production instance's `.env` still holds the secrets, and it is still the operator's to protect. The compose file refuses to start without a JWT secret and a payment provider.
- A developer who edits `.env` by hand and sets `ENV=production` locally gets a refusal, because the fake provider is not allowed there. The local stack is a local stack.
- The local stack's database password is no longer `spn`, so a script that assumed the default has to read `.env`. That is the point.
- The webhook key for the local fake provider is generated, so the local stack and the local tests have to agree on it. The test suite sets it explicitly for the whole session.
- The rules in these files are checked by tests that read the files, so a rule that is only in a file is a rule that is checked.

## Revisit trigger

If the platform ever runs more than one instance, the forwarded address and the mode have to be per instance rather than per file, and the loopback binding and the single-instance rate limiter would have to be revisited too.
