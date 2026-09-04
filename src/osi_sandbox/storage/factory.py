"""Build a storage backend from settings, enforcing the auth policy.

Policy: ``local`` needs no auth; every other backend requires a PAT / API
token (or cloud API credentials). Encryption, when enabled, requires a key.
Any violation raises at construction time so runs fail closed rather than
silently writing sensitive outputs to an unauthenticated destination.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from osi_sandbox.storage.base import StorageBackend
from osi_sandbox.storage.encrypted import EncryptedStorageBackend
from osi_sandbox.storage.errors import StorageConfigError
from osi_sandbox.storage.local import LocalStorageBackend

if TYPE_CHECKING:
    from osi_sandbox.config import Settings

_VALID_BACKENDS = ("local", "s3", "http")


def _build_base(settings: Settings) -> StorageBackend:
    backend = (settings.storage_backend or "local").lower()
    if backend not in _VALID_BACKENDS:
        raise StorageConfigError(
            f"unknown STORAGE_BACKEND={backend!r} (expected one of {_VALID_BACKENDS})"
        )

    if backend == "local":
        return LocalStorageBackend(Path(settings.data_dir))

    if backend == "http":
        from osi_sandbox.storage.http_token import HttpTokenStorageBackend

        return HttpTokenStorageBackend(
            base_url=settings.storage_http_url or "",
            token=settings.storage_http_token,
            verify=settings.storage_http_verify_tls,
        )

    if backend == "s3":
        from osi_sandbox.storage.s3 import S3StorageBackend

        return S3StorageBackend(
            bucket=settings.storage_s3_bucket or "",
            prefix=settings.storage_s3_prefix or "",
            endpoint_url=settings.storage_s3_endpoint_url,
            region=settings.storage_s3_region,
            access_key_id=settings.storage_s3_access_key_id,
            secret_access_key=settings.storage_s3_secret_access_key,
            session_token=settings.storage_s3_session_token,
        )

    raise StorageConfigError(f"unhandled backend {backend!r}")  # pragma: no cover


def build_storage(settings: Settings) -> StorageBackend:
    """Construct the (optionally encrypted) storage backend for ``settings``."""
    base = _build_base(settings)
    if settings.storage_encryption:
        return EncryptedStorageBackend(base, settings.storage_encryption_key or "")
    return base


def describe_storage(settings: Settings) -> dict[str, Any]:
    """Return a non-secret summary of the configured storage, plus validity.

    Never includes token/credential/key values — only whether they are present.
    """
    backend = (settings.storage_backend or "local").lower()
    encryption = bool(settings.storage_encryption)

    if backend == "local":
        auth_required = False
        auth_configured = True
    elif backend == "http":
        auth_required = True
        auth_configured = bool(settings.storage_http_token)
    elif backend == "s3":
        auth_required = True
        auth_configured = bool(
            settings.storage_s3_access_key_id and settings.storage_s3_secret_access_key
        )
    else:
        auth_required = True
        auth_configured = False

    summary: dict[str, Any] = {
        "backend": backend,
        "encrypted": encryption,
        "encryption_key_configured": bool(settings.storage_encryption_key),
        "auth": "pat_or_api_token" if auth_required else "none",
        "auth_required": auth_required,
        "auth_configured": auth_configured,
    }
    try:
        built = build_storage(settings)
        summary["ok"] = True
        summary["kind"] = built.kind
    except Exception as exc:  # noqa: BLE001 - surface config errors as status
        summary["ok"] = False
        summary["error"] = str(exc)
    return summary
