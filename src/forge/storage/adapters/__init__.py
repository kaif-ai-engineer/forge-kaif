from __future__ import annotations

from forge.storage.adapters.azure import AzureAdapter
from forge.storage.adapters.base import FileInfo, StorageBackend, normalize_path
from forge.storage.adapters.gcs import GCSAdapter
from forge.storage.adapters.local import LocalFilesystemAdapter
from forge.storage.adapters.s3 import S3Adapter

__all__ = [
    "AzureAdapter",
    "FileInfo",
    "GCSAdapter",
    "LocalFilesystemAdapter",
    "S3Adapter",
    "StorageBackend",
    "normalize_path",
]
