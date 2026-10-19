from pathlib import Path
from typing import Any

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError


class S3Storage:
    def __init__(
        self,
        *,
        endpoint_url: str | None,
        bucket: str,
        access_key: str,
        secret_key: str,
    ) -> None:
        self._endpoint_url = endpoint_url
        self._bucket = bucket
        self._access_key = access_key
        self._secret_key = secret_key
        self._client: Any = None
        self._bucket_ready = False

    def put_file(self, key: str, path: Path) -> None:
        self._ensure_bucket()
        self.client.upload_file(str(path), self._bucket, key)

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self._bucket, Key=key)

    def presigned_get_url(
        self,
        key: str,
        *,
        expires_seconds: int = 300,
        download_filename: str | None = None,
    ) -> str:
        params: dict[str, Any] = {"Bucket": self._bucket, "Key": key}
        if download_filename is not None:
            safe_name = download_filename.replace('"', "").replace("\r", "").replace("\n", "")
            params["ResponseContentDisposition"] = f'attachment; filename="{safe_name}"'
        url: str = self.client.generate_presigned_url(
            "get_object", Params=params, ExpiresIn=expires_seconds
        )
        return url

    def health(self) -> bool:
        """Is the object storage reachable and usable?

        A bucket that does not exist yet is not a failure. The bucket is
        created on first use, and a fresh deployment has to pass its
        readiness check before anything has been uploaded, so a missing
        bucket is created here too. A bucket that exists but cannot be
        reached is a failure.
        """
        try:
            self.client.head_bucket(Bucket=self._bucket)
        except ClientError as exc:
            if not _is_missing_bucket(exc):
                return False
            try:
                self.client.create_bucket(Bucket=self._bucket)
            except (BotoCoreError, ClientError):
                return False
            self._bucket_ready = True
            return True
        except BotoCoreError:
            return False
        return True

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = boto3.client(
                "s3",
                endpoint_url=self._endpoint_url,
                aws_access_key_id=self._access_key,
                aws_secret_access_key=self._secret_key,
                region_name="us-east-1",
                config=BotoConfig(signature_version="s3v4"),
            )
        return self._client

    def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        try:
            self.client.head_bucket(Bucket=self._bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self._bucket)
        self._bucket_ready = True


def _is_missing_bucket(exc: ClientError) -> bool:
    """Is this error "the bucket is not there" rather than "no access"?"""
    code = str(exc.response.get("Error", {}).get("Code", ""))
    return code in {"404", "NoSuchBucket", "NotFound"}
