"""The rules the deployment files have to hold.

A compose file, a Caddyfile and a workflow are not code the
application runs, but they are code the deployment runs, and they are
where several of the platform's guarantees live: which addresses are
published, which mode the application starts in, and which image is
deployed. A rule that is only in a file is a rule that nothing checks.

These are the tests for those rules. They read the files from the
repository, so they run where the repository is checked out and are
skipped where it is not.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = next(
    (
        parent
        for parent in Path(__file__).resolve().parents
        if (parent / "docker-compose.prod.yml").is_file()
    ),
    None,
)

pytestmark = pytest.mark.skipif(
    REPO_ROOT is None, reason="the deployment files are not in this checkout"
)


def _read(relative: str) -> str:
    assert REPO_ROOT is not None
    return (REPO_ROOT / relative).read_text()


def test_the_production_stack_pins_the_mode() -> None:
    """The production-only checks are keyed on ENV, so ENV is pinned.

    The compose file says what the mode is, rather than leaving it to an
    untracked file on the instance. A Compose "environment" entry
    overrides "env_file", so the two cannot disagree.
    """
    compose = _read("docker-compose.prod.yml")

    assert compose.count("ENV: production") >= 2
    assert 'TESTING_ENDPOINTS_ENABLED: "false"' in compose


def test_the_production_stack_does_not_trust_every_forwarded_address() -> None:
    """The forwarded address is only believed from the proxy.

    A wildcard would let any client choose the address the rate limiter
    keys on, which is a way around the limit and not just a nuisance.
    """
    compose = _read("docker-compose.prod.yml")

    assert "--forwarded-allow-ips=*" not in compose
    assert "forwarded-allow-ips" in compose


def test_the_production_stack_needs_a_real_jwt_secret() -> None:
    """The placeholder secret is refused in production, so it has to be set."""
    compose = _read("docker-compose.prod.yml")

    assert "JWT_SECRET: ${JWT_SECRET:?" in compose
    assert "PAYMENT_PROVIDER: ${PAYMENT_PROVIDER:?" in compose


def test_the_edge_does_not_trust_the_forwarded_address() -> None:
    """Caddy sets the forwarded scheme and address itself.

    A global "trusted_proxies" list that includes the private ranges
    would let a client on the instance's own network choose the address
    the application sees.
    """
    caddyfile = _read("infra/Caddyfile")

    assert "trusted_proxies" not in caddyfile


def test_the_edge_caps_the_body_it_forwards() -> None:
    """The edge limit is above the application's own limit.

    The application accepts a file of MAX_UPLOAD_MB and refuses a body
    over that plus a megabyte of envelope. An edge limit below the
    application's would refuse files the application would have taken.
    """
    caddyfile = _read("infra/Caddyfile")

    match = re.search(r"max_size\s+(\d+)MB", caddyfile)
    assert match is not None, "the edge does not cap the body it forwards"
    assert int(match.group(1)) >= 54


def test_the_development_stack_publishes_nothing_but_loopback() -> None:
    """The local stack is for the developer, not for the network.

    Every published port is bound to the loopback address, so the
    database, the object store, the API and the database browser are
    not reachable from the network the developer's laptop is on.
    """
    compose = _read("docker-compose.yml")

    published = re.findall(r'^\s*-\s*"([^"]*:\d+:\d+)"', compose, re.MULTILINE)
    assert published, "no published ports were found, so the rule is not being checked"
    for mapping in published:
        host = mapping.split(":")[0]
        assert host == "127.0.0.1", f"{mapping} is published on every interface"


def test_the_development_stack_needs_its_credentials() -> None:
    """The published defaults are not the credentials the stack runs on."""
    compose = _read("docker-compose.yml")

    assert "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?" in compose
    assert "MINIO_ROOT_PASSWORD: ${S3_SECRET_KEY:?" in compose


def test_the_deployment_runs_the_reviewed_commit() -> None:
    """The deployed code is the code that was reviewed.

    A dispatch can choose any ref, so the workflow checks the ref itself
    rather than relying on the branch protection of main.
    """
    workflow = _read(".github/workflows/deploy.yml")

    assert "ref: ${{ github.sha }}" in workflow
    assert "refs/heads/main" in workflow


def test_the_deployment_pins_both_images() -> None:
    """Both images are named by the commit they were built from.

    The frontend was published under a mutable tag that no workflow
    built, so the origin ran something other than what was reviewed.
    """
    workflow = _read(".github/workflows/deploy.yml")

    assert "WEB_IMAGE: ghcr.io/${{ github.repository }}/web" in workflow
    assert "WEB_TAG: ${{ github.sha }}" in workflow
    assert 'export SPN_WEB_IMAGE="$WEB_IMAGE_TAG"' in workflow
    assert 'export SPN_API_IMAGE="$IMAGE_TAG"' in workflow


def test_the_deployment_builds_the_frontend() -> None:
    """The web image is built by the workflow, not only referenced."""
    workflow = _read(".github/workflows/deploy.yml")

    assert "context: frontend" in workflow
    assert "file: frontend/Dockerfile.prod" in workflow


def test_the_example_environment_holds_placeholders_only() -> None:
    """The values that ship in the template are not working secrets.

    The template is in the repository, so anything in it is public. The
    local stack generates its own secrets, and the production stack
    refuses to start without real ones.
    """
    example = _read(".env.example")

    assert "JWT_SECRET=local-dev-placeholder-change-me" in example
    assert "FAKE_WEBHOOK_SECRET=local-dev-placeholder-change-me" in example
    assert "PAYMENT_PROVIDER=fake" in example


def test_the_local_secrets_are_generated_rather_than_shipped() -> None:
    """A fresh checkout gets generated secrets.

    The values in the template are public, so the local stack replaces
    them with generated ones, and leaves alone anything the developer
    has already changed.
    """
    script = _read("infra/scripts/generate-dev-secrets.sh")

    assert "FAKE_WEBHOOK_SECRET" in script
    assert "openssl rand" in script


def test_the_backup_is_only_readable_by_the_operator() -> None:
    """A dump is a complete copy of the credential store."""
    script = _read("infra/scripts/backup.sh")

    assert "umask 077" in script
    assert "chmod 600" in script
    assert "--acl private" in script


def test_the_restore_drill_cannot_drop_the_live_database() -> None:
    """The drill drops the database it restores into, so it checks the name."""
    script = _read("infra/scripts/restore-drill.sh")

    assert "refusing to run" in script
    assert "printenv POSTGRES_DB" in script
