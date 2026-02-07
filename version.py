"""Version helpers for the API."""

from __future__ import annotations

import os
from importlib import metadata

DEFAULT_APP_VERSION = "0.0.0"
APP_VERSION_ENV = "APP_VERSION"


def _load_package_version(package_name: str) -> str | None:
    try:
        return metadata.version(package_name)
    except metadata.PackageNotFoundError:
        return None


def _resolve_app_version() -> str:
    # Prefer package metadata when available; fall back to env or default.
    package_name = os.environ.get("APP_PACKAGE_NAME")
    if package_name:
        pkg_version = _load_package_version(package_name)
        if pkg_version:
            return pkg_version
    return os.environ.get(APP_VERSION_ENV, DEFAULT_APP_VERSION)


APP_VERSION = _resolve_app_version()

# Only change when the API contract changes.
API_SCHEMA_VERSION = "2024-10-01"
