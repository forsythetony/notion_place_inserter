"""Cloudflare R2 (S3-compatible) object storage for media assets."""

from __future__ import annotations

import os
from typing import Any

from loguru import logger


def normalize_r2_key_prefix(value: str | None) -> str:
    """Strip whitespace and leading/trailing slashes so oleo, /oleo/, oleo/ all become oleo."""
    if not value:
        return ""
    return value.strip().strip("/")


def join_prefixed_object_key(prefix: str, relative_key: str) -> str:
    """Join optional prefix with a relative object key (no leading slash on result)."""
    rel = relative_key.lstrip("/")
    p = normalize_r2_key_prefix(prefix)
    if not p:
        return rel
    return f"{p}/{rel}"


class R2MediaStorageService:
    """Upload/delete objects in an R2 bucket; build public URLs for CDN or R2.dev domains."""

    def __init__(
        self,
        *,
        endpoint_url: str,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
        public_base_url: str,
        key_prefix: str = "",
        region: str = "auto",
    ) -> None:
        import boto3  # lazy import so tests can skip if unused

        self._bucket = bucket
        self._key_prefix = normalize_r2_key_prefix(key_prefix)
        self._public_base_url = public_base_url.rstrip("/")
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
        )

    @classmethod
    def from_env(cls) -> R2MediaStorageService | None:
        endpoint = os.environ.get("R2_ENDPOINT_URL", "").strip()
        key_id = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
        secret = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
        bucket = os.environ.get("R2_BUCKET_NAME", "").strip()
        public_base = os.environ.get("R2_PUBLIC_BASE_URL", "").strip()
        key_prefix = os.environ.get("R2_KEY_PREFIX", "").strip()
        if not (endpoint and key_id and secret and bucket and public_base):
            logger.warning(
                "r2_media_storage_disabled | missing one of R2_ENDPOINT_URL, "
                "R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME, R2_PUBLIC_BASE_URL"
            )
            return None
        return cls(
            endpoint_url=endpoint,
            access_key_id=key_id,
            secret_access_key=secret,
            bucket=bucket,
            public_base_url=public_base,
            key_prefix=key_prefix,
        )

    @property
    def key_prefix(self) -> str:
        return self._key_prefix

    def prefixed_object_key(self, relative_key: str) -> str:
        """Build the full S3 object key (prefix + relative path under the bucket)."""
        return join_prefixed_object_key(self._key_prefix, relative_key)

    def public_url_for_key(self, storage_key: str) -> str:
        key = storage_key.lstrip("/")
        return f"{self._public_base_url}/{key}"

    def put_object(self, *, key: str, body: bytes, content_type: str) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )

    def delete_object(self, *, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def head_bucket(self) -> dict[str, Any]:
        """Cheap connectivity check (caller may ignore errors)."""
        return self._client.head_bucket(Bucket=self._bucket)
