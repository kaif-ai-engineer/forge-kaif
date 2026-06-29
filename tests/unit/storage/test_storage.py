from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from forge.storage.adapters.base import FileInfo, detect_content_type, normalize_path
from forge.storage.adapters.local import LocalFilesystemAdapter
from forge.storage.exceptions import (
    StorageDownloadError,
    StorageNotFoundError,
    StoragePermissionError,
    StorageUploadError,
)
from forge.storage.module import StorageModule

# ── Helpers ───────────────────────────────────────────────────────────


@pytest.fixture
def temp_base() -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def local_adapter(temp_base: str) -> LocalFilesystemAdapter:
    return LocalFilesystemAdapter(base_path=temp_base)


@pytest.fixture
def sample_file() -> tuple[str, str]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("hello world")
        tmp_path = f.name
    yield tmp_path, "hello world"
    Path(tmp_path).unlink(missing_ok=True)


# ── normalize_path ────────────────────────────────────────────────────


class TestNormalizePath:
    def test_strips_leading_slash(self) -> None:
        assert normalize_path("/foo/bar") == "foo/bar"

    def test_converts_backslashes(self) -> None:
        assert normalize_path("foo\\bar\\baz") == "foo/bar/baz"

    def test_strips_trailing_slash(self) -> None:
        assert normalize_path("foo/bar/") == "foo/bar"

    def test_empty_string(self) -> None:
        assert normalize_path("") == ""

    def test_already_normalized(self) -> None:
        assert normalize_path("foo/bar/baz.txt") == "foo/bar/baz.txt"


# ── detect_content_type ──────────────────────────────────────────────


class TestDetectContentType:
    def test_txt_file(self) -> None:
        assert detect_content_type("file.txt") == "text/plain"

    def test_json_file(self) -> None:
        assert detect_content_type("data.json") == "application/json"

    def test_png_image(self) -> None:
        assert detect_content_type("image.png") == "image/png"

    def test_unknown_extension(self) -> None:
        assert detect_content_type("file.unknown") == "application/octet-stream"

    def test_no_extension(self) -> None:
        assert detect_content_type("Makefile") == "application/octet-stream"


# ── LocalFilesystemAdapter ───────────────────────────────────────────


class TestLocalFilesystemAdapter:
    @pytest.mark.asyncio
    async def test_upload_and_download(
        self, local_adapter: LocalFilesystemAdapter, sample_file: tuple[str, str], temp_base: str
    ) -> None:
        local_path, content = sample_file
        remote = "test/hello.txt"

        info = await local_adapter.upload(local_path, remote)
        assert info.path == "test/hello.txt"
        assert info.size == len(content)
        assert info.content_type == "text/plain"

        assert await local_adapter.exists(remote)

        dest = str(Path(temp_base) / "downloaded.txt")
        downloaded = await local_adapter.download(remote, dest)
        assert Path(downloaded).exists()
        assert Path(downloaded).read_text() == content
        Path(dest).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_upload_with_custom_content_type(
        self, local_adapter: LocalFilesystemAdapter, sample_file: tuple[str, str]
    ) -> None:
        local_path, _ = sample_file
        info = await local_adapter.upload(local_path, "custom", content_type="application/json")
        assert info.content_type == "application/json"

    @pytest.mark.asyncio
    async def test_upload_with_metadata(
        self, local_adapter: LocalFilesystemAdapter, sample_file: tuple[str, str]
    ) -> None:
        local_path, _ = sample_file
        info = await local_adapter.upload(
            local_path, "meta", metadata={"author": "test", "version": "1"}
        )
        assert info.metadata == {"author": "test", "version": "1"}

    @pytest.mark.asyncio
    async def test_upload_nonexistent_source(self, local_adapter: LocalFilesystemAdapter) -> None:
        with pytest.raises(StorageUploadError, match="does not exist"):
            await local_adapter.upload("/nonexistent/path.txt", "remote")

    @pytest.mark.asyncio
    async def test_download_nonexistent_remote(
        self, local_adapter: LocalFilesystemAdapter, temp_base: str
    ) -> None:
        with pytest.raises(StorageNotFoundError, match="does not exist"):
            await local_adapter.download("nonexistent", str(Path(temp_base) / "out"))

    @pytest.mark.asyncio
    async def test_download_overwrite_protection(
        self, local_adapter: LocalFilesystemAdapter, sample_file: tuple[str, str], temp_base: str
    ) -> None:
        local_path, _ = sample_file
        await local_adapter.upload(local_path, "test/file.txt")

        dest = str(Path(temp_base) / "overwrite_test.txt")
        await local_adapter.download("test/file.txt", dest)

        with pytest.raises(StorageDownloadError, match="already exists"):
            await local_adapter.download("test/file.txt", dest)

        result = await local_adapter.download("test/file.txt", dest, overwrite=True)
        assert Path(result).exists()
        Path(dest).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_delete(
        self, local_adapter: LocalFilesystemAdapter, sample_file: tuple[str, str]
    ) -> None:
        local_path, _ = sample_file
        await local_adapter.upload(local_path, "test/to_delete.txt")

        assert await local_adapter.exists("test/to_delete.txt")
        assert await local_adapter.delete("test/to_delete.txt") is True
        assert await local_adapter.exists("test/to_delete.txt") is False

        assert await local_adapter.delete("test/nonexistent") is False

    @pytest.mark.asyncio
    async def test_list(
        self, local_adapter: LocalFilesystemAdapter, sample_file: tuple[str, str]
    ) -> None:
        local_path, _ = sample_file
        await local_adapter.upload(local_path, "a/file1.txt")
        await local_adapter.upload(local_path, "a/file2.txt")
        await local_adapter.upload(local_path, "b/file3.txt")

        all_items = await local_adapter.list()
        assert len(all_items) == 3

        a_items = await local_adapter.list("a/")
        assert len(a_items) == 2

        b_items = await local_adapter.list("b/")
        assert len(b_items) == 1

    @pytest.mark.asyncio
    async def test_list_non_recursive(
        self, local_adapter: LocalFilesystemAdapter, sample_file: tuple[str, str]
    ) -> None:
        local_path, _ = sample_file
        await local_adapter.upload(local_path, "root.txt")
        await local_adapter.upload(local_path, "sub/deep/file.txt")

        items = await local_adapter.list(recursive=False)
        paths = {f.path for f in items}
        assert "root.txt" in paths
        assert "sub/deep/file.txt" not in paths

    @pytest.mark.asyncio
    async def test_list_empty_prefix(self, local_adapter: LocalFilesystemAdapter) -> None:
        items = await local_adapter.list("nonexistent/")
        assert items == []

    @pytest.mark.asyncio
    async def test_exists(
        self, local_adapter: LocalFilesystemAdapter, sample_file: tuple[str, str]
    ) -> None:
        local_path, _ = sample_file
        await local_adapter.upload(local_path, "exists_test.txt")

        assert await local_adapter.exists("exists_test.txt") is True
        assert await local_adapter.exists("nonexistent.txt") is False

    @pytest.mark.asyncio
    async def test_presigned_url(
        self, local_adapter: LocalFilesystemAdapter, sample_file: tuple[str, str]
    ) -> None:
        local_path, _ = sample_file
        await local_adapter.upload(local_path, "presigned_test.txt")

        url = await local_adapter.presigned_url("presigned_test.txt")
        assert url.startswith("file://")
        assert "presigned_test.txt" in url

    @pytest.mark.asyncio
    async def test_presigned_url_nonexistent(self, local_adapter: LocalFilesystemAdapter) -> None:
        with pytest.raises(StorageNotFoundError, match="does not exist"):
            await local_adapter.presigned_url("nonexistent.txt")

    @pytest.mark.asyncio
    async def test_path_traversal_prevention(self, local_adapter: LocalFilesystemAdapter) -> None:
        with pytest.raises(StoragePermissionError, match="Path traversal"):
            await local_adapter.exists("../etc/passwd")

    @pytest.mark.asyncio
    async def test_upload_creates_intermediate_dirs(
        self, local_adapter: LocalFilesystemAdapter, sample_file: tuple[str, str]
    ) -> None:
        local_path, _ = sample_file
        deep_path = "a/b/c/d/deep_file.txt"
        info = await local_adapter.upload(local_path, deep_path)
        assert info.path == deep_path
        assert await local_adapter.exists(deep_path)

    @pytest.mark.asyncio
    async def test_file_info_dataclass(self) -> None:
        from datetime import UTC, datetime

        dt = datetime.now(UTC)
        info = FileInfo(
            path="test.txt",
            size=100,
            last_modified=dt,
            content_type="text/plain",
            etag="abc123",
            metadata={"key": "val"},
        )
        assert info.path == "test.txt"
        assert info.size == 100
        assert info.last_modified == dt
        assert info.content_type == "text/plain"
        assert info.etag == "abc123"
        assert info.metadata == {"key": "val"}


# ── StorageModule ─────────────────────────────────────────────────────


class TestStorageModule:
    @pytest.mark.asyncio
    async def test_module_init_with_local_default(
        self, temp_base: str, sample_file: tuple[str, str]
    ) -> None:
        module = StorageModule()
        module._backend = LocalFilesystemAdapter(base_path=temp_base)

        local_path, content = sample_file
        info = await module.upload(local_path, "test/hello.txt")
        assert info.path == "test/hello.txt"
        assert info.content_type == "text/plain"

        assert await module.exists("test/hello.txt")

        dest = str(Path(temp_base) / "dl_module.txt")
        dl = await module.download("test/hello.txt", dest)
        assert Path(dl).exists()
        assert Path(dl).read_text() == content
        Path(dest).unlink(missing_ok=True)

        items = await module.list("test/")
        assert len(items) == 1

        assert await module.delete("test/hello.txt") is True
        assert await module.exists("test/hello.txt") is False

    def test_backend_property_uninitialized(self) -> None:
        module = StorageModule()
        with pytest.raises(RuntimeError, match="not initialized"):
            _ = module.backend

    def test_health_check_uninitialized(self) -> None:
        module = StorageModule()
        from forge.core.module import HealthResult

        hr = module.health_check()
        assert hr.status == HealthResult.ERROR

    def test_health_check_local(self, temp_base: str) -> None:
        module = StorageModule()
        module._backend = LocalFilesystemAdapter(base_path=temp_base)
        from forge.core.module import HealthResult

        hr = module.health_check()
        assert hr.status == HealthResult.OK


class TestMimeTypeDetection:
    @pytest.mark.asyncio
    async def test_html_upload(self, local_adapter: LocalFilesystemAdapter) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
            f.write("<html></html>")
            tmp = f.name
        try:
            info = await local_adapter.upload(tmp, "page.html")
            assert info.content_type == "text/html"
        finally:
            Path(tmp).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_python_upload(self, local_adapter: LocalFilesystemAdapter) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("x = 1")
            tmp = f.name
        try:
            info = await local_adapter.upload(tmp, "script.py")
            assert info.content_type == "text/x-python"
        finally:
            Path(tmp).unlink(missing_ok=True)
