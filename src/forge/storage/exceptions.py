from __future__ import annotations


class StorageError(Exception):
    """Base exception for all storage-related errors."""


class StorageConnectionError(StorageError):
    """Raised when a connection to a storage backend fails."""


class StorageNotFoundError(StorageError):
    """Raised when a remote path does not exist."""


class StoragePermissionError(StorageError):
    """Raised when access to a storage resource is denied."""


class StorageUploadError(StorageError):
    """Raised when an upload operation fails."""


class StorageDownloadError(StorageError):
    """Raised when a download operation fails."""


class StorageDeleteError(StorageError):
    """Raised when a delete operation fails."""


class StorageListError(StorageError):
    """Raised when a list operation fails."""
