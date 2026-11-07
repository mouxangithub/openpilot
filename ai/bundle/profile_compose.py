"""G8 ordered profile/bundle patch-layer composition with conflict diagnostics.

Composes configuration from ordered sources into a merged config:

  bundles (ordered) → bundle patch layers → profile patch layer → launcher layer

Higher layers override lower ones. A conflict is when two layers in the SAME
group (e.g. two bundles) set the same key to different values — reported
structurally (``ERR_PROFILE_CONFLICT``) rather than silently picking one.
Composition is pure (no writes to the running process), so it is idempotent
and testable offline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ai.core.errors import ERR_PROFILE_CONFLICT

# Stable op vocabulary for patch operations.
OP_SET = "set"
OP_DELETE = "delete"


@dataclass
class PatchLayer:
  order: int
  source: str   # bundle id | profile | launcher
  operations: list[dict[str, Any]] = field(default_factory=list)

  def to_dict(self) -> dict[str, Any]:
    return {"order": self.order, "source": self.source, "operations": list(self.operations)}


def _op_key(op: dict[str, Any]) -> str:
  return str(op.get("path", ""))


class ProfileComposer:
  """Compose ordered patch layers into a merged config with diagnostics.

  ``resolve_bundle`` maps a bundle id -> BundleManifest (or a dict-like with
  :meth:`patch_operations`). ``get_profile_config`` maps a profile id -> dict.
  Defaults raise a structured error when a source cannot be resolved, which the
  caller may override for offline tests.
  """

  def __init__(
    self,
    bundle_loader: Any = None,
    profile_manager: Any = None,
    *,
    resolve_bundle: Callable[[str], Any] | None = None,
    get_profile_config: Callable[[str], dict[str, Any]] | None = None,
  ) -> None:
    self.bundle_loader = bundle_loader
    self.profile_manager = profile_manager
    self._resolve_bundle = resolve_bundle or self._default_resolve_bundle
    self._get_profile_config = get_profile_config or self._default_profile_config

  def _default_resolve_bundle(self, bundle_id: str) -> Any:
    if self.bundle_loader is None or not hasattr(self.bundle_loader, "load"):
      raise KeyError(f"no bundle resolver for {bundle_id!r}")
    raise KeyError(f"cannot auto-resolve installed bundle {bundle_id!r} by id; provide resolve_bundle")

  def _default_profile_config(self, profile_id: str) -> dict[str, Any]:
    if self.profile_manager is None or not hasattr(self.profile_manager, "get"):
      return {}
    try:
      profile = self.profile_manager.get(None, profile_id)
      if profile is None:
        return {}
      data = getattr(profile, "config", None) or getattr(profile, "to_dict", lambda: {})()
      return dict(data) if isinstance(data, dict) else {}
    except Exception:
      return {}

  def _layers_for_bundles(self, bundles: list[str]) -> list[PatchLayer]:
    layers: list[PatchLayer] = []
    for order, bundle_id in enumerate(bundles):
      manifest = self._resolve_bundle(bundle_id)
      ops = manifest.patch_operations() if hasattr(manifest, "patch_operations") else []
      layers.append(PatchLayer(order=order, source=bundle_id, operations=[dict(o) for o in ops]))
    return layers

  def preview(self, profile_id: str, bundles: list[str]) -> list[PatchLayer]:
    """Return the ordered patch layers for diagnostics/preview (no merge)."""
    layers = self._layers_for_bundles(bundles)
    profile_layer = PatchLayer(
      order=len(layers),
      source="profile",
      operations=[{"op": OP_SET, "path": k, "value": v} for k, v in self._get_profile_config(profile_id).items()],
    )
    layers.append(profile_layer)
    return layers

  def compose(self, profile_id: str, bundles: list[str]) -> tuple[dict[str, Any], list[str]]:
    """Merge layers in order. Returns (merged_config, conflict_msgs).

    Conflicts only flagged between layers sharing the same source group (two
    bundles setting the same key to different values). Profile/launcher layers
    legitimately override bundles.
    """
    layers = self.preview(profile_id, bundles)
    merged: dict[str, Any] = {}
    conflicts: list[str] = []
    seen_sources: dict[str, dict[str, Any]] = {}
    for layer in layers:
      for op in layer.operations:
        path = _op_key(op)
        value = op.get("value")
        if op.get("op") == OP_DELETE:
          merged.pop(path, None)
          continue
        if path in merged and layer.source not in ("profile", "launcher"):
          prior = seen_sources.get(path)
          if prior is not None and prior["value"] != value:
            conflicts.append(
              f"{ERR_PROFILE_CONFLICT}: key '{path}' set to different values "
              f"by '{prior['source']}' and '{layer.source}'"
            )
        merged[path] = value
        seen_sources[path] = {"source": layer.source, "value": value}
    return merged, conflicts

  def has_conflicts(self, profile_id: str, bundles: list[str]) -> bool:
    _, conflicts = self.compose(profile_id, bundles)
    return bool(conflicts)