"""Regression: ``ai.server.op_routes.setup_routes()`` is a true fallback layer.

In ``ai/server/app_factory.py`` the authoritative production router
(``ai.server.routes.register_routes``) is registered first and
``setup_routes`` runs afterwards as a fallback. aiohttp permits duplicate
path+method registration and silently shadows the earlier one (first wins),
so any endpoint re-registered by the fallback becomes unreachable dead code.

These tests pin the contract:
- standalone (local-dev) the fallback registers its unique entry points;
- production-first the fallback never re-registers an existing endpoint;
- the registration is idempotent (running it twice changes nothing).
"""
from __future__ import annotations

import unittest
from collections import Counter

import ai.tests.bootstrap_pc  # noqa: F401  (installs openpilot mocks)

from aiohttp import web


def _signatures(app: web.Application) -> list[tuple[str, str]]:
  """Return ``(METHOD, canonical_path)`` for each non-system router entry."""
  sigs: list[tuple[str, str]] = []
  for route in app.router.routes():
    method = getattr(route, "method", "") or ""
    resource = getattr(route, "resource", None)
    canonical = getattr(resource, "canonical", None)
    if canonical is None:
      continue  # system route (built-in 404/405, static mount)
    sigs.append((method.upper(), canonical))
  return sigs


class TestOpRoutesStandalone(unittest.TestCase):
  """The local-dev server (ai/server/app.py) registers only setup_routes."""

  def test_registers_local_dev_entrypoints(self):
    from ai.server.op_routes import setup_routes
    app = web.Application()
    setup_routes(app)
    sigs = set(_signatures(app))
    self.assertIn(("GET", "/tools-panel"), sigs)
    self.assertIn(("POST", "/api/ai/tool"), sigs)
    self.assertIn(("GET", "/api/ai/health"), sigs)
    self.assertIn(("POST", "/api/ai/chat/completions"), sigs)

  def test_catchall_fallback_registered(self):
    from ai.server.op_routes import setup_routes
    app = web.Application()
    setup_routes(app)
    # aiohttp canonicalizes the ``{tail:.*}`` pattern to ``{tail}``.
    self.assertTrue(
      any(method == "*" and path == "/api/ai/{tail}" for method, path in _signatures(app))
    )

  def test_standalone_router_has_no_duplicates(self):
    from ai.server.op_routes import setup_routes
    app = web.Application()
    setup_routes(app)
    sigs = _signatures(app)
    self.assertEqual(len(sigs), len(set(sigs)))

  def test_setup_routes_is_idempotent(self):
    from ai.server.op_routes import setup_routes
    app = web.Application()
    setup_routes(app)
    first = Counter(_signatures(app))
    setup_routes(app)
    second = Counter(_signatures(app))
    self.assertEqual(first, second)


class TestOpRoutesAsFallback(unittest.TestCase):
  """Production routes are registered first; setup_routes must not shadow them."""

  def _app_with_production_routes(self) -> web.Application:
    from ai.server.routes import register_routes
    app = web.Application()
    # register_routes / register_agent_routes read these app keys eagerly.
    app["params"] = None
    app["config"] = None
    register_routes(app, json_response=web.json_response)
    return app

  def test_precondition_production_routes_present(self):
    """Guard: fail loudly if the production router is unavailable here."""
    before = set(_signatures(self._app_with_production_routes()))
    self.assertIn(("GET", "/api/ai/status"), before)
    self.assertIn(("POST", "/api/ai/chat"), before)

  def test_fallback_does_not_reregister_existing(self):
    from ai.server.op_routes import setup_routes
    app = self._app_with_production_routes()
    before = Counter(_signatures(app))
    setup_routes(app)
    after = Counter(_signatures(app))
    # No pre-existing path+method may have its registration count increased.
    for sig, count in before.items():
      self.assertEqual(after.get(sig, 0), count, f"setup_routes re-registered {sig}")

  def test_overlapping_endpoints_stay_single(self):
    from ai.server.op_routes import setup_routes
    app = self._app_with_production_routes()
    setup_routes(app)
    after = Counter(_signatures(app))
    for sig in [
      ("GET", "/api/ai/status"),
      ("GET", "/api/ai/bootstrap"),
      ("POST", "/api/ai/chat"),
      ("GET", "/api/ai/config"),
      ("GET", "/api/ai/providers"),
      ("GET", "/api/ai/sessions"),
      ("POST", "/api/ai/write/confirm"),
      ("GET", "/api/ai/tools"),
      ("GET", "/api/ai/files/content"),
      ("GET", "/api/ai/skills/registry"),
    ]:
      self.assertEqual(after[sig], 1, f"expected exactly one registration for {sig}")

  def test_fallback_still_adds_local_dev_only_endpoints(self):
    from ai.server.op_routes import setup_routes
    app = self._app_with_production_routes()
    setup_routes(app)
    after = Counter(_signatures(app))
    self.assertEqual(after[("GET", "/tools-panel")], 1)
    self.assertEqual(after[("POST", "/api/ai/tool")], 1)
    self.assertEqual(after[("*", "/api/ai/{tail}")], 1)


if __name__ == "__main__":
  unittest.main()
