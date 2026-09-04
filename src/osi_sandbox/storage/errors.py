"""Storage error types."""

from __future__ import annotations


class StorageError(Exception):
    """Base class for storage failures."""


class StorageConfigError(StorageError):
    """Storage backend is misconfigured (missing or invalid settings)."""


class StorageAuthError(StorageError):
    """A non-local backend was requested without a PAT / API token / credentials."""
