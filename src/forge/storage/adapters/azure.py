from __future__ import annotations

from datetime import UTC, datetime, timedelta
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


class AzureAdapter:
    """
    Storage adapter backed by Azure Blob Storage.

    Uses the *azure-storage-blob* library.
    """

    def __init__(
        self,
        container: str,
        *,
        connection_string: str | None = None,
        account_url: str | None = None,
        credential: str | None = None,
    ) -> None:
        from azure.storage.blob import BlobServiceClient

        if connection_string:
            self._service = BlobServiceClient.from_connection_string(connection_string)
        elif account_url:
            self._service = BlobServiceClient(account_url=account_url, credential=credential)
        else:
            raise ValueError(
                "Either connection_string or account_url must be provided for AzureAdapter"
            )

        self._container_name = container
        self._container_client = self._service.get_container_client(container)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _key(self, remote_path: str) -> str:
        return normalize_path(remote_path)

    def _file_info_from_blob(self, blob: Any) -> FileInfo:
        last_mod = blob.last_modified
        return FileInfo(
            path=blob.name,
            size=blob.size or 0,
            last_modified=last_mod.replace(tzinfo=UTC) if last_mod else None,
            content_type=blob.content_settings.content_type if blob.content_settings else None,
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
        from azure.storage.blob import ContentSettings

        key = self._key(remote_path)
        ct = content_type or detect_content_type(local_path)

        blob_client = self._container_client.get_blob_client(key)
        content_settings = ContentSettings(content_type=ct)

        file_size = Path(local_path).stat().st_size

        try:
            with Path(local_path).open("rb") as data:
                if file_size > multipart_threshold:
                    blob_client.upload_blob(
                        data,
                        overwrite=True,
                        content_settings=content_settings,
                        metadata=metadata,
                        max_concurrency=4,
                    )
                else:
                    blob_client.upload_blob(
                        data,
                        overwrite=True,
                        content_settings=content_settings,
                        metadata=metadata,
                    )
        except Exception as exc:
            raise StorageUploadError(
                f"Failed to upload {local_path} to azure://{self._container_name}/{key}: {exc}"
            ) from exc

        props = blob_client.get_blob_properties()
        return self._file_info_from_blob(props)

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

        blob_client = self._container_client.get_blob_client(key)

        try:
            with dst.open("wb") as data:
                stream = blob_client.download_blob()
                stream.readinto(data)
        except Exception as exc:
            raise StorageDownloadError(
                f"Failed to download azure://{self._container_name}/{key} to {local_path}: {exc}"
            ) from exc

        return str(dst.resolve())

    async def delete(
        self,
        remote_path: str,
    ) -> bool:
        key = self._key(remote_path)
        blob_client = self._container_client.get_blob_client(key)

        if not await self.exists(remote_path):
            return False
        try:
            blob_client.delete_blob()
            return True
        except Exception as exc:
            raise StorageDeleteError(
                f"Failed to delete azure://{self._container_name}/{key}: {exc}"
            ) from exc

    async def list(
        self,
        prefix: str = "",
        *,
        recursive: bool = True,
    ) -> list[FileInfo]:
        key_prefix = self._key(prefix)
        items: list[FileInfo] = []

        try:
            blobs = self._container_client.list_blobs(name_starts_with=key_prefix)
            for blob in blobs:
                name: str = blob.name
                if not recursive and "/" in name[len(key_prefix):].lstrip("/"):
                    continue
                items.append(self._file_info_from_blob(blob))
        except Exception as exc:
            raise StorageListError(
                f"Failed to list objects at prefix {prefix} in container {self._container_name}: {exc}"
            ) from exc

        items.sort(key=lambda f: f.path)
        return items

    async def exists(
        self,
        remote_path: str,
    ) -> bool:
        key = self._key(remote_path)
        blob_client = self._container_client.get_blob_client(key)
        try:
            blob_client.get_blob_properties()
            return True
        except Exception as exc:
            error_code = getattr(exc, "error_code", None)
            if error_code == "BlobNotFound":
                return False
            raise StorageConnectionError(
                f"Failed to check existence of azure://{self._container_name}/{key}: {exc}"
            ) from exc

    async def presigned_url(
        self,
        remote_path: str,
        *,
        expiration: int = 3600,
    ) -> str:
        from azure.storage.blob import BlobSasPermissions, generate_blob_sas

        key = self._key(remote_path)
        blob_client = self._container_client.get_blob_client(key)

        if not await self.exists(remote_path):
            raise StorageNotFoundError(
                f"Object does not exist: azure://{self._container_name}/{key}"
            )

        try:
            user_delegation_key = None
            sas_token = generate_blob_sas(
                account_name=self._service.account_name,
                container_name=self._container_name,
                blob_name=key,
                account_key=self._service.credential.account_key
                if hasattr(self._service.credential, "account_key")
                else None,
                user_delegation_key=user_delegation_key,
                permission=BlobSasPermissions(read=True),
                expiry=datetime.now(UTC) + timedelta(seconds=expiration),
            )
            url = f"{blob_client.url}?{sas_token}"
            return url
        except Exception as exc:
            raise StorageConnectionError(
                f"Failed to generate SAS URL for azure://{self._container_name}/{key}: {exc}"
            ) from exc
