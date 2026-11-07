"""G12 centralized config schema registry, validator and stable error codes."""
from __future__ import annotations

from ai.config.registry import ConfigRegistry, SchemaField
from ai.config.validator import validate_payload, collect_errors

__all__ = ["ConfigRegistry", "SchemaField", "validate_payload", "collect_errors"]