from __future__ import annotations

import mimetypes
import shutil
from datetime import UTC, datetime
from pathlib import Path

from forge.storage.adapters.base import FileInfo, detect_content_type, normalize_path
from forge.storage.exceptions import (
    StorageDeleteError,
    StorageDownloadError,
    StorageListError,
    StorageNotFoundError,
    StoragePermissionError,
    StorageUploadError,
)


class LocalFilesystemAdapter:
    """
    Storage adapter backed by the local filesystem.

    Designed for development and testing. All remote paths are resolved
    relative to the configured *base_path*.
    """

    def __init__(self, base_path: str | Path = "/tmp/forge-storage") -> None:
        self._base_path = Path(base_path).resolve()
        self._base_path.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve(self, remote_path: str) -> Path:
        normalized = normalize_path(remote_path)
        resolved = (self._base_path / normalized).resolve()
        if not str(resolved).startswith(str(self._base_path)):
            raise StoragePermissionError(f"Path traversal detected: {remote_path}")
        return resolved

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
        src = Path(local_path)
        if not src.is_file():
            raise StorageUploadError(f"Local source does not exist or is not a file: {local_path}")

        dst = self._resolve(remote_path)
        dst.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copy2(str(src), str(dst))
        except OSError as exc:
            raise StorageUploadError(
                f"Failed to upload {local_path} -> {remote_path}: {exc}"
            ) from exc

        ct = content_type or detect_content_type(local_path)
        stat = dst.stat()
        return FileInfo(
            path=normalize_path(remote_path),
            size=stat.st_size,
            last_modified=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            content_type=ct,
            metadata=metadata or {},
        )

    async def download(
        self,
        remote_path: str,
        local_path: str,
        *,
        overwrite: bool = False,
    ) -> str:
        src = self._resolve(remote_path)
        if not src.is_file():
            raise StorageNotFoundError(f"Remote path does not exist: {remote_path}")

        dst = Path(local_path)
        if dst.exists() and not overwrite:
            raise StorageDownloadError(
                f"Local file already exists: {local_path} (use overwrite=True to replace)"
            )
        dst.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copy2(str(src), str(dst))
        except OSError as exc:
            raise StorageDownloadError(
                f"Failed to download {remote_path} -> {local_path}: {exc}"
            ) from exc

        return str(dst.resolve())

    async def delete(
        self,
        remote_path: str,
    ) -> bool:
        path = self._resolve(remote_path)
        if not path.exists():
            return False
        try:
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(str(path))
            else:
                return False
        except OSError as exc:
            raise StorageDeleteError(f"Failed to delete {remote_path}: {exc}") from exc
        return True

    async def list(
        self,
        prefix: str = "",
        *,
        recursive: bool = True,
    ) -> list[FileInfo]:
        resolved = self._resolve(prefix)
        if not resolved.exists():
            return []

        items: list[FileInfo] = []
        pattern = "**/*" if recursive else "*"

        try:
            for entry in resolved.glob(pattern):
                if not entry.is_file():
                    continue
                rel_path = entry.relative_to(self._base_path).as_posix()
                stat = entry.stat()
                ct, _ = mimetypes.guess_type(str(entry))
                items.append(
                    FileInfo(
                        path=rel_path,
                        size=stat.st_size,
                        last_modified=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                        content_type=ct or "application/octet-stream",
                    )
                )
        except OSError as exc:
            raise StorageListError(f"Failed to list objects at prefix {prefix}: {exc}") from exc

        items.sort(key=lambda f: f.path)
        return items

    async def exists(
        self,
        remote_path: str,
    ) -> bool:
        return self._resolve(remote_path).exists()

    async def presigned_url(
        self,
        remote_path: str,
        *,
        expiration: int = 3600,
    ) -> str:
        resolved = self._resolve(remote_path)
        if not resolved.is_file():
            raise StorageNotFoundError(f"Remote path does not exist: {remote_path}")
        return resolved.as_uri()
