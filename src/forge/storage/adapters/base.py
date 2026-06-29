from __future__ import annotations

import abc
import mimetypes
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class FileInfo:
    """Metadata for a single object returned by list operations."""

    path: str
    size: int = 0
    last_modified: datetime | None = None
    content_type: str | None = None
    etag: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


def normalize_path(path: str) -> str:
    """Normalize a storage path to use forward slashes and strip leading slash."""
    normalized = path.replace("\\", "/").replace(os.sep, "/").strip("/")
    return normalized


def detect_content_type(file_path: str, default: str = "application/octet-stream") -> str:
    """Detect the MIME type of a file based on its extension."""
    content_type, _ = mimetypes.guess_type(file_path)
    return content_type or default


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol that every storage adapter must implement."""

    @abc.abstractmethod
    async def upload(
        self,
        local_path: str,
        remote_path: str,
        *,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
        multipart_threshold: int = 100 * 1024 * 1024,
    ) -> FileInfo:
        ...

    @abc.abstractmethod
    async def download(
        self,
        remote_path: str,
        local_path: str,
        *,
        overwrite: bool = False,
    ) -> str:
        ...

    @abc.abstractmethod
    async def delete(
        self,
        remote_path: str,
    ) -> bool:
        ...

    @abc.abstractmethod
    async def list(
        self,
        prefix: str = "",
        *,
        recursive: bool = True,
    ) -> list[FileInfo]:
        ...

    @abc.abstractmethod
    async def exists(
        self,
        remote_path: str,
    ) -> bool:
        ...

    @abc.abstractmethod
    async def presigned_url(
        self,
        remote_path: str,
        *,
        expiration: int = 3600,
    ) -> str:
        ...
