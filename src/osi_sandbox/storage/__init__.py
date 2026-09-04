"""Pluggable storage backends for snapshots, analysis, and agentic outputs.

Backends:
- ``local``    filesystem (no authentication)
- ``s3``       S3-compatible object storage (boto3) — requires API credentials
- ``http``     token-authenticated REST object store — requires a PAT / API token

Any backend may be wrapped with transparent client-side encryption.

Policy: every non-local backend MUST be authenticated with a PAT / API token
(or equivalent cloud API credentials). Misconfiguration fails closed at
construction time — see :func:`osi_sandbox.storage.factory.build_storage`.
"""

from __future__ import annotations

from osi_sandbox.storage.base import StorageBackend
from osi_sandbox.storage.errors import StorageAuthError, StorageConfigError, StorageError
from osi_sandbox.storage.factory import build_storage, describe_storage

__all__ = [
    "StorageBackend",
    "StorageError",
    "StorageAuthError",
    "StorageConfigError",
    "build_storage",
    "describe_storage",
]
