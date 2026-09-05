"""Named W1 entry point for actual release-calendar PIT validation."""

from __future__ import annotations

from .base import temporal_metadata_for_spec

# Keep the W1-facing name explicit while using the single canonical validator.
actual_release_metadata = temporal_metadata_for_spec

__all__ = ["actual_release_metadata"]
