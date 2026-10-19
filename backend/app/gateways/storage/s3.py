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
        try:
            self.client.head_bucket(Bucket=self._bucket)
        except (BotoCoreError, ClientError):
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
