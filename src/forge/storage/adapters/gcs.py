from __future__ import annotations

from datetime import UTC
from pathlib import Path
from typing import Any

from forge.storage.adapters.base import FileInfo, detect_content_type, normalize_path
from forge.storage.exceptions import (
    StorageConnectionError,
    StorageDeleteError,
    StorageDownloadError,
    StorageListError,
    StorageNotFoundError,
    StorageUploadError,
)


class GCSAdapter:
    """
    Storage adapter backed by Google Cloud Storage.

    Uses the *google-cloud-storage* library.
    """

    def __init__(
        self,
        bucket: str,
        *,
        project: str | None = None,
        credentials_path: str | None = None,
    ) -> None:
        from google.cloud import storage

        if credentials_path:
            self._client = storage.Client.from_service_account_json(
                credentials_path, project=project
            )
        else:
            self._client = storage.Client(project=project)

        self._bucket = self._client.bucket(bucket)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _key(self, remote_path: str) -> str:
        return normalize_path(remote_path)

    def _file_info_from_blob(self, blob: Any) -> FileInfo:
        last_mod = blob.updated
        return FileInfo(
            path=blob.name,
            size=blob.size or 0,
            last_modified=last_mod.replace(tzinfo=UTC) if last_mod else None,
            content_type=blob.content_type or "application/octet-stream",
            etag=blob.etag.strip('"') if blob.etag else None,
            metadata=dict(blob.metadata) if blob.metadata else {},
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def upload(
        self,
        local_path: str,
        remote_path: str,
        *,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
        multipart_threshold: int = 100 * 1024 * 1024,
    ) -> FileInfo:
        key = self._key(remote_path)
        ct = content_type or detect_content_type(local_path)

        blob = self._bucket.blob(key)
        if metadata:
            blob.metadata = metadata

        try:
            blob.upload_from_filename(
                local_path,
                content_type=ct,
                if_generation_match=None,
            )
        except Exception as exc:
            raise StorageUploadError(
                f"Failed to upload {local_path} to gs://{self._bucket.name}/{key}: {exc}"
            ) from exc

        blob.reload()
        return self._file_info_from_blob(blob)

    async def download(
        self,
        remote_path: str,
        local_path: str,
        *,
        overwrite: bool = False,
    ) -> str:
        key = self._key(remote_path)
        dst = Path(local_path)

        if dst.exists() and not overwrite:
            raise StorageDownloadError(
                f"Local file already exists: {local_path} (use overwrite=True to replace)"
            )

        dst.parent.mkdir(parents=True, exist_ok=True)

        blob = self._bucket.blob(key)
        if not blob.exists():
            raise StorageNotFoundError(f"Object does not exist: gs://{self._bucket.name}/{key}")

        try:
            blob.download_to_filename(local_path)
        except Exception as exc:
            raise StorageDownloadError(
                f"Failed to download gs://{self._bucket.name}/{key} to {local_path}: {exc}"
            ) from exc

        return str(dst.resolve())

    async def delete(
        self,
        remote_path: str,
    ) -> bool:
        key = self._key(remote_path)
        blob = self._bucket.blob(key)
        if not blob.exists():
            return False
        try:
            blob.delete()
            return True
        except Exception as exc:
            raise StorageDeleteError(
                f"Failed to delete gs://{self._bucket.name}/{key}: {exc}"
            ) from exc

    async def list(
        self,
        prefix: str = "",
        *,
        recursive: bool = True,
    ) -> list[FileInfo]:
        key_prefix = self._key(prefix)
        delimiter = None if recursive else "/"

        try:
            blobs = self._client.list_blobs(
                self._bucket.name,
                prefix=key_prefix,
                delimiter=delimiter,
            )
            items = [self._file_info_from_blob(blob) for blob in blobs]
        except Exception as exc:
            raise StorageListError(
                f"Failed to list objects at prefix {prefix} in bucket {self._bucket.name}: {exc}"
            ) from exc

        items.sort(key=lambda f: f.path)
        return items

    async def exists(
        self,
        remote_path: str,
    ) -> bool:
        key = self._key(remote_path)
        blob = self._bucket.blob(key)
        try:
            result: bool = blob.exists()
            return result
        except Exception as exc:
            raise StorageConnectionError(
                f"Failed to check existence of gs://{self._bucket.name}/{key}: {exc}"
            ) from exc

    async def presigned_url(
        self,
        remote_path: str,
        *,
        expiration: int = 3600,
    ) -> str:
        key = self._key(remote_path)
        blob = self._bucket.blob(key)
        if not blob.exists():
            raise StorageNotFoundError(f"Object does not exist: gs://{self._bucket.name}/{key}")
        try:
            url: str = blob.generate_signed_url(
                expiration=expiration,
                method="GET",
            )
            return url
        except Exception as exc:
            raise StorageConnectionError(
                f"Failed to generate signed URL for gs://{self._bucket.name}/{key}: {exc}"
            ) from exc
