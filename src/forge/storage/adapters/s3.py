from __future__ import annotations

from datetime import UTC
from pathlib import Path
from typing import Any

from boto3.s3.transfer import TransferConfig

from forge.storage.adapters.base import FileInfo, detect_content_type, normalize_path
from forge.storage.exceptions import (
    StorageConnectionError,
    StorageDeleteError,
    StorageDownloadError,
    StorageListError,
    StorageNotFoundError,
    StorageUploadError,
)


class S3Adapter:
    """
    Storage adapter backed by AWS S3 (or S3-compatible) object storage.

    Uses *boto3* under the hood. Multipart upload is automatically used
    for files above *multipart_threshold*.
    """

    def __init__(
        self,
        bucket: str,
        *,
        region: str | None = None,
        endpoint_url: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        session_token: str | None = None,
        **kwargs: Any,
    ) -> None:
        import boto3

        self._bucket = bucket
        session_kwargs: dict[str, Any] = {}
        if region:
            session_kwargs["region_name"] = region
        if access_key_id and secret_access_key:
            session_kwargs["aws_access_key_id"] = access_key_id
            session_kwargs["aws_secret_access_key"] = secret_access_key
        if session_token:
            session_kwargs["aws_session_token"] = session_token

        session = boto3.Session(**session_kwargs)

        client_kwargs: dict[str, Any] = {}
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url
        client_kwargs.update(kwargs)

        self._client = session.client("s3", **client_kwargs)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _key(self, remote_path: str) -> str:
        return normalize_path(remote_path)

    def _file_info_from_head(self, remote_path: str, head: dict[str, Any]) -> FileInfo:
        ct = head.get("ContentType") or "application/octet-stream"
        last_mod = head.get("LastModified")
        return FileInfo(
            path=normalize_path(remote_path),
            size=head.get("ContentLength", 0),
            last_modified=last_mod.replace(tzinfo=UTC) if last_mod else None,
            content_type=ct,
            etag=head.get("ETag", "").strip('"'),
            metadata=head.get("Metadata", {}),
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

        extra_args: dict[str, Any] = {}
        if ct:
            extra_args["ContentType"] = ct
        if metadata:
            extra_args["Metadata"] = metadata

        file_size = Path(local_path).stat().st_size
        config_kwargs: dict[str, Any] = {}
        if file_size > multipart_threshold:
            config_kwargs = {
                "multipart_threshold": multipart_threshold,
                "multipart_chunksize": min(multipart_threshold // 2, 50 * 1024 * 1024),
            }

        try:
            transfer_config = TransferConfig(**config_kwargs) if config_kwargs else None
            self._client.upload_file(
                local_path,
                self._bucket,
                key,
                ExtraArgs=extra_args or None,
                Config=transfer_config,
            )
        except Exception as exc:
            raise StorageUploadError(
                f"Failed to upload {local_path} to s3://{self._bucket}/{key}: {exc}"
            ) from exc

        head = self._client.head_object(Bucket=self._bucket, Key=key)
        return self._file_info_from_head(remote_path, head)

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

        try:
            self._client.download_file(self._bucket, key, local_path)
        except self._client.exceptions.NoSuchKey as exc:
            raise StorageNotFoundError(f"Object does not exist: s3://{self._bucket}/{key}") from exc
        except Exception as exc:
            raise StorageDownloadError(
                f"Failed to download s3://{self._bucket}/{key} to {local_path}: {exc}"
            ) from exc

        return str(dst.resolve())

    async def delete(
        self,
        remote_path: str,
    ) -> bool:
        key = self._key(remote_path)
        if not await self.exists(remote_path):
            return False
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
            return True
        except Exception as exc:
            raise StorageDeleteError(f"Failed to delete s3://{self._bucket}/{key}: {exc}") from exc

    async def list(
        self,
        prefix: str = "",
        *,
        recursive: bool = True,
    ) -> list[FileInfo]:
        key_prefix = self._key(prefix)
        items: list[FileInfo] = []

        paginator = self._client.get_paginator("list_objects_v2")
        try:
            page_iterator = paginator.paginate(Bucket=self._bucket, Prefix=key_prefix)
            for page in page_iterator:
                contents = page.get("Contents", [])
                for obj in contents:
                    obj_key: str = obj["Key"]
                    if not recursive and "/" in obj_key[len(key_prefix) :].lstrip("/"):
                        continue
                    last_mod = obj.get("LastModified")
                    items.append(
                        FileInfo(
                            path=obj_key,
                            size=obj.get("Size", 0),
                            last_modified=last_mod.replace(tzinfo=UTC) if last_mod else None,
                            etag=obj.get("ETag", "").strip('"'),
                        )
                    )
        except Exception as exc:
            raise StorageListError(
                f"Failed to list objects at prefix {prefix} in bucket {self._bucket}: {exc}"
            ) from exc

        items.sort(key=lambda f: f.path)
        return items

    async def exists(
        self,
        remote_path: str,
    ) -> bool:
        key = self._key(remote_path)
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except self._client.exceptions.ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code in {"404", "NoSuchKey"}:
                return False
            raise StorageConnectionError(
                f"Failed to check existence of s3://{self._bucket}/{key}: {exc}"
            ) from exc

    async def presigned_url(
        self,
        remote_path: str,
        *,
        expiration: int = 3600,
    ) -> str:
        key = self._key(remote_path)
        if not await self.exists(remote_path):
            raise StorageNotFoundError(f"Object does not exist: s3://{self._bucket}/{key}")
        try:
            url: str = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expiration,
            )
            return url
        except Exception as exc:
            raise StorageConnectionError(
                f"Failed to generate presigned URL for s3://{self._bucket}/{key}: {exc}"
            ) from exc
