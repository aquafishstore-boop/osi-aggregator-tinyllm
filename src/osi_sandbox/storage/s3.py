"""S3-compatible object storage backend (AWS S3, Cloudflare R2, MinIO, ...).

Auth uses cloud API credentials (access key id + secret, optionally a session
token). Credentials are required; constructing without them raises
:class:`StorageAuthError`. ``boto3`` is an optional dependency
(``pip install 'osi-sandbox[s3]'``).
"""

from __future__ import annotations

from osi_sandbox.storage.base import StorageBackend, normalize_key
from osi_sandbox.storage.errors import StorageAuthError, StorageConfigError, StorageError


class S3StorageBackend(StorageBackend):
    kind = "s3"

    def __init__(
        self,
        bucket: str,
        *,
        prefix: str = "",
        endpoint_url: str | None = None,
        region: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        session_token: str | None = None,
    ) -> None:
        if not bucket:
            raise StorageConfigError("s3 storage backend requires STORAGE_S3_BUCKET")
        if not (access_key_id and secret_access_key):
            raise StorageAuthError(
                "s3 storage backend requires API credentials "
                "(STORAGE_S3_ACCESS_KEY_ID + STORAGE_S3_SECRET_ACCESS_KEY)"
            )
        try:
            import boto3  # type: ignore
        except ImportError as exc:
            raise StorageConfigError(
                "s3 backend requires boto3 — install with 'pip install osi-sandbox[s3]'"
            ) from exc

        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            region_name=region or None,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            aws_session_token=session_token or None,
        )

    def _full(self, key: str) -> str:
        norm = normalize_key(key)
        return f"{self.prefix}/{norm}" if self.prefix else norm

    def put_bytes(self, key: str, data: bytes) -> None:
        self._client.put_object(Bucket=self.bucket, Key=self._full(key), Body=data)

    def get_bytes(self, key: str) -> bytes | None:
        from botocore.exceptions import ClientError  # type: ignore

        try:
            resp = self._client.get_object(Bucket=self.bucket, Key=self._full(key))
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("NoSuchKey", "404", "NotFound"):
                return None
            raise StorageError(f"s3 get {key} failed: {code}") from exc
        return resp["Body"].read()

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError  # type: ignore

        try:
            self._client.head_object(Bucket=self.bucket, Key=self._full(key))
            return True
        except ClientError:
            return False

    def list_children(self, prefix: str) -> list[str]:
        norm_prefix = "" if prefix in ("", "/") else normalize_key(prefix)
        full_prefix = self._full(norm_prefix) if norm_prefix else self.prefix
        full_prefix = (full_prefix + "/") if full_prefix else ""
        paginator = self._client.get_paginator("list_objects_v2")
        children: set[str] = set()
        for page in paginator.paginate(
            Bucket=self.bucket, Prefix=full_prefix, Delimiter="/"
        ):
            for cp in page.get("CommonPrefixes", []):
                name = cp["Prefix"][len(full_prefix):].rstrip("/")
                if name:
                    children.add(name)
            for obj in page.get("Contents", []):
                name = obj["Key"][len(full_prefix):]
                if name and "/" not in name:
                    children.add(name)
        return sorted(children)
