import os
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest
from app.config import get_settings
from app.gateways.storage import S3Storage
from botocore.exceptions import BotoCoreError, ClientError


@pytest.fixture
def s3_storage() -> S3Storage:
    settings = get_settings()
    storage = S3Storage(
        endpoint_url=settings.s3_endpoint_url or None,
        bucket=settings.s3_bucket,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
    )
    try:
        storage.client.list_buckets()
    except (BotoCoreError, ClientError) as exc:
        if os.environ.get("SPN_REQUIRE_S3"):
            raise
        pytest.skip(f"S3 endpoint not reachable: {exc}")
    return storage


def test_put_presign_download_delete_round_trip(s3_storage: S3Storage, tmp_path: Path) -> None:
    key = f"tests/{uuid.uuid4().hex}.pdf"
    path = tmp_path / "round-trip.pdf"
    path.write_bytes(b"%PDF-1.7 round trip test")

    s3_storage.put_file(key, path)
    assert s3_storage.health()

    url = s3_storage.presigned_get_url(key, expires_seconds=60, download_filename="round trip.pdf")
    with urllib.request.urlopen(url, timeout=10) as response:
        assert response.read() == path.read_bytes()
        disposition = response.headers.get("Content-Disposition", "")
        assert "attachment" in disposition
        assert "round trip.pdf" in disposition

    s3_storage.delete(key)

    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(s3_storage.presigned_get_url(key, expires_seconds=60), timeout=10)
    assert excinfo.value.code == 404


def test_a_bucket_that_does_not_exist_yet_is_created_and_reported_healthy(
    s3_storage: S3Storage,
) -> None:
    missing = f"tests-missing-{uuid.uuid4().hex}"
    storage = S3Storage(
        endpoint_url=get_settings().s3_endpoint_url or None,
        bucket=missing,
        access_key=get_settings().s3_access_key,
        secret_key=get_settings().s3_secret_key,
    )

    assert storage.health() is True
    assert storage.client.head_bucket(Bucket=missing)
    storage.client.delete_bucket(Bucket=missing)


def test_a_bucket_that_cannot_be_reached_is_reported_unhealthy(
    s3_storage: S3Storage,
) -> None:
    storage = S3Storage(
        endpoint_url="http://127.0.0.1:1",
        bucket="spn-files",
        access_key=get_settings().s3_access_key,
        secret_key=get_settings().s3_secret_key,
    )

    assert storage.health() is False
