from __future__ import annotations

import base64
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from .config import get_settings


class StorageService:
    """Persist uploaded clinical documents using the configured backend."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def _filesystem_path(self, key: str) -> Path:
        if not key or key.startswith("/") or ".." in Path(key).parts:
            raise ValueError("Unsafe storage key detected")
        base_dir = Path("storage") / "uploads"
        target = base_dir / key
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def _safe_filename(self, filename: str) -> str:
        candidate = (filename or "document").strip()
        if not candidate or candidate in {".", ".."} or "/" in candidate or "\\" in candidate or ".." in Path(candidate).parts:
            raise ValueError("Unsafe storage filename")
        return candidate

    def _validate_storage_target(self, *, storage_backend: str, bucket: str) -> None:
        if storage_backend.lower() == "s3":
            normalized = (bucket or "").strip()
            if not normalized:
                raise ValueError("S3 bucket is required when STORAGE_BACKEND=s3")

    def save_document(self, *, organization_id: str, patient_id: str, filename: str, content: bytes | str, content_type: str = "application/octet-stream") -> tuple[str, str]:
        safe_filename = self._safe_filename(filename)
        if content_type not in self.settings.allowed_upload_content_types:
            raise ValueError("Unsupported upload content type")
        if self.settings.storage_backend.lower() == "s3":
            self._validate_storage_target(storage_backend=self.settings.storage_backend, bucket=self.settings.s3_bucket)
        payload = content.encode("utf-8") if isinstance(content, str) else content
        if len(payload) > self.settings.max_upload_bytes:
            raise ValueError("Upload exceeds the configured size limit")
        storage_prefix = (self.settings.storage_prefix or "careos").strip().strip("/")
        key = f"{storage_prefix}/{organization_id}/{patient_id}/{datetime.now(timezone.utc).strftime('%Y%m%d')}/{uuid4().hex}-{safe_filename}"

        if self.settings.storage_backend.lower() == "s3":
            try:
                import boto3
            except ModuleNotFoundError as exc:  # pragma: no cover - dependency is optional for non-S3 deployments
                raise RuntimeError("boto3 is required when STORAGE_BACKEND=s3") from exc

            client = boto3.client(
                "s3",
                region_name=self.settings.s3_region,
                aws_access_key_id=self.settings.s3_access_key_id or None,
                aws_secret_access_key=self.settings.s3_secret_access_key or None,
            )
            client.put_object(
                Bucket=self.settings.s3_bucket,
                Key=key,
                Body=payload,
                ContentType=content_type,
            )
            url = f"https://{self.settings.s3_bucket}.s3.{self.settings.s3_region}.amazonaws.com/{key}"
            return key, url

        target = self._filesystem_path(key)
        target.write_bytes(payload)
        url = f"{self.settings.app_url}/storage/{key}"
        return key, url

    def read_document(self, key: str) -> bytes:
        self._validate_key(key)
        if self.settings.storage_backend.lower() == "s3":
            try:
                import boto3
            except ModuleNotFoundError as exc:  # pragma: no cover
                raise RuntimeError("boto3 is required when STORAGE_BACKEND=s3") from exc
            client = boto3.client(
                "s3",
                region_name=self.settings.s3_region,
                aws_access_key_id=self.settings.s3_access_key_id or None,
                aws_secret_access_key=self.settings.s3_secret_access_key or None,
            )
            response = client.get_object(Bucket=self.settings.s3_bucket, Key=key)
            body = response.get("Body")
            if body is None:
                raise FileNotFoundError(key)
            return body.read()

        return self._filesystem_path(key).read_bytes()

    def delete_document(self, key: str) -> None:
        self._validate_key(key)
        if self.settings.storage_backend.lower() == "s3":
            try:
                import boto3
            except ModuleNotFoundError as exc:  # pragma: no cover
                raise RuntimeError("boto3 is required when STORAGE_BACKEND=s3") from exc
            client = boto3.client(
                "s3",
                region_name=self.settings.s3_region,
                aws_access_key_id=self.settings.s3_access_key_id or None,
                aws_secret_access_key=self.settings.s3_secret_access_key or None,
            )
            client.delete_object(Bucket=self.settings.s3_bucket, Key=key)
            return

        target = self._filesystem_path(key)
        if target.exists():
            target.unlink()

    def _validate_key(self, key: str) -> None:
        if not key or key.startswith("/") or ".." in Path(key).parts or "\\" in key:
            raise ValueError("Unsafe storage key detected")
