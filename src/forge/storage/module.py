from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, cast

from forge.core.module import ForgeModule, HealthResult
from forge.storage.adapters.base import FileInfo, StorageBackend
from forge.storage.adapters.local import LocalFilesystemAdapter
from forge.storage.exceptions import StorageError

if TYPE_CHECKING:
    from forge.core.runtime import ForgeRuntime as Runtime


class StorageModule(ForgeModule):
    """Manages object storage services with pluggable backend adapters."""

    name = "storage"
    dependencies: ClassVar[list[str]] = ["config"]

    def __init__(self) -> None:
        super().__init__()
        self._backend: StorageBackend | None = None
        self._runtime: Runtime | None = None

    @property
    def backend(self) -> StorageBackend:
        if self._backend is None:
            raise RuntimeError("Storage module is not initialized.")
        return self._backend

    async def setup(self, runtime: Runtime) -> None:
        self._runtime = runtime

        from forge.config.module import ConfigModule

        config_module = cast("ConfigModule", runtime.get(ConfigModule))
        config = getattr(config_module.config, "storage", None)

        backend_type = "local"
        local_base_path = "/tmp/forge-storage"
        s3_bucket: str | None = None
        s3_region: str | None = None
        s3_endpoint: str | None = None
        gcs_bucket: str | None = None
        gcs_project: str | None = None
        gcs_credentials: str | None = None
        azure_container: str | None = None
        azure_connection_string: str | None = None

        if config is not None:
            backend_type = getattr(config, "backend", "local")
            local_base_path = getattr(config, "local_base_path", "/tmp/forge-storage")
            s3_config = getattr(config, "s3", None)
            if s3_config is not None:
                s3_bucket = getattr(s3_config, "bucket", None)
                s3_region = getattr(s3_config, "region", None)
                s3_endpoint = getattr(s3_config, "endpoint_url", None)
            gcs_config = getattr(config, "gcs", None)
            if gcs_config is not None:
                gcs_bucket = getattr(gcs_config, "bucket", None)
                gcs_project = getattr(gcs_config, "project", None)
                gcs_credentials = getattr(gcs_config, "credentials_path", None)
            azure_config = getattr(config, "azure", None)
            if azure_config is not None:
                azure_container = getattr(azure_config, "container", None)
                azure_connection_string = getattr(azure_config, "connection_string", None)

        if backend_type == "s3":
            from forge.storage.adapters.s3 import S3Adapter

            if not s3_bucket:
                raise StorageError("S3 backend requires a 'bucket' configuration.")
            self._backend = S3Adapter(
                bucket=s3_bucket,
                region=s3_region,
                endpoint_url=s3_endpoint,
            )
        elif backend_type == "gcs":
            from forge.storage.adapters.gcs import GCSAdapter

            if not gcs_bucket:
                raise StorageError("GCS backend requires a 'bucket' configuration.")
            self._backend = GCSAdapter(
                bucket=gcs_bucket,
                project=gcs_project,
                credentials_path=gcs_credentials,
            )
        elif backend_type == "azure":
            from forge.storage.adapters.azure import AzureAdapter

            if not azure_container:
                raise StorageError("Azure backend requires a 'container' configuration.")
            self._backend = AzureAdapter(
                container=azure_container,
                connection_string=azure_connection_string,
            )
        else:
            self._backend = LocalFilesystemAdapter(base_path=local_base_path)

    async def teardown(self) -> None:
        self._backend = None
        self._runtime = None

    # ------------------------------------------------------------------
    # Public API — delegates to the active backend
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
        return await self.backend.upload(
            local_path,
            remote_path,
            content_type=content_type,
            metadata=metadata,
            multipart_threshold=multipart_threshold,
        )

    async def download(
        self,
        remote_path: str,
        local_path: str,
        *,
        overwrite: bool = False,
    ) -> str:
        return await self.backend.download(remote_path, local_path, overwrite=overwrite)

    async def delete(self, remote_path: str) -> bool:
        return await self.backend.delete(remote_path)

    async def list(
        self,
        prefix: str = "",
        *,
        recursive: bool = True,
    ) -> list[FileInfo]:
        return await self.backend.list(prefix, recursive=recursive)

    async def exists(self, remote_path: str) -> bool:
        return await self.backend.exists(remote_path)

    async def presigned_url(
        self,
        remote_path: str,
        *,
        expiration: int = 3600,
    ) -> str:
        return await self.backend.presigned_url(remote_path, expiration=expiration)

    def health_check(self) -> HealthResult:
        backend = self._backend
        if backend is None:
            return HealthResult.error("Storage backend not initialized")

        if isinstance(backend, LocalFilesystemAdapter):
            return HealthResult(HealthResult.OK, "Local filesystem storage active")

        try:
            from forge.core.async_bridge import run_async_health_check

            async def _ping() -> None:
                await backend.exists("health-check-probe")

            run_async_health_check(_ping())
            return HealthResult.ok()
        except Exception as exc:
            return HealthResult.error(f"Storage backend health check failed: {exc}")
