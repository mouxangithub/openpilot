"""Self-check suite for the mutation testing infrastructure (mutation.py).

Intent (adapted from StarPilot test_mutation_infra.py): the mutation gate
itself is safety-critical tooling — a broken mutator silently turns every
mutant into "survived" or, worse, "killed", corrupting the whole signal.
These tests pin down the pure-python core (site enumeration accounting,
instrumentation invariants, target ordering, outcome classification) on any
host, plus an end-to-end enumerate->instrument->compile->toggle run wherever
a C toolchain and tree_sitter are available.
"""
import ctypes
import shutil
import subprocess
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import MagicMock, patch

from opendbc.safety.tests import mutation

HAVE_CC = shutil.which("cc") is not None


def _site(site_id=0, expr_start=0, expr_end=0, op_start=0, op_end=0,
          original="==", mutated="!=", mutator="comparison",
          origin_file=Path("opendbc/safety/helpers.h"), origin_line=1):
  return mutation.MutationSite(
    site_id=site_id, expr_start=expr_start, expr_end=expr_end,
    op_start=op_start, op_end=op_end, line=1,
    original_op=original, mutated_op=mutated, mutator=mutator,
    origin_file=mutation.ROOT / origin_file if not origin_file.is_absolute() else origin_file,
    origin_line=origin_line)


class TestParseIntLiteral(unittest.TestCase):
  def test_decimal_hex_and_suffixes(self):
    self.assertEqual(mutation._parse_int_literal("3"), (3, "dec", ""))
    self.assertEqual(mutation._parse_int_literal("0x10U"), (16, "hex", "U"))
    self.assertEqual(mutation._parse_int_literal("0X2fLU"), (47, "hex", "LU"))
    self.assertEqual(mutation._parse_int_literal("12u"), (12, "dec", "u"))

  def test_non_literals_rejected(self):
    self.assertIsNone(mutation._parse_int_literal("abc"))
    self.assertIsNone(mutation._parse_int_literal("1.5"))
    self.assertIsNone(mutation._parse_int_literal(""))


class TestInstrumentSource(unittest.TestCase):
  def test_simple_comparison_is_wrapped_in_selecting_ternary(self):
    source = "int ok(int v) { return v == 3; }"
    start = source.index("v == 3")
    end = start + len("v == 3")
    site = _site(0, start, end, start + 2, start + 4)
    out = mutation._instrument_source(source, [site])
    expected_expr = "(__mutation_active_id == 0) ? (v != 3) : (v == 3)"
    self.assertIn(expected_expr, out)
    # original text outside the expression untouched
    self.assertIn("int ok(int v) { return ", out)

  def test_nested_sites_form_containment_forest(self):
    source = "(a == b) <= c"
    outer = _site(0, 0, 13, 9, 11, "<=", ">")
    inner = _site(1, 0, 8, 3, 5, "==", "!=")
    out = mutation._instrument_source(source, [inner, outer])
    # inner ternary is inlined into BOTH branches of the outer ternary, so it
    # appears twice; the outer selector appears once.
    self.assertEqual(out.count("__mutation_active_id == 0"), 1)
    self.assertEqual(out.count("__mutation_active_id == 1"), 2)
    self.assertIn("(a != b)", out)   # inner mutated expression
    self.assertIn("(a == b)", out)   # inner original preserved
    self.assertIn("> c", out)        # outer mutated expression
    self.assertIn("<= c", out)       # outer original preserved

  def test_operator_mismatch_is_asserted_not_silently_miscompiled(self):
    source = "a == b"
    site = _site(0, 0, len(source), 2, 4, original="+")  # wrong original op
    with self.assertRaisesRegex(AssertionError, "Operator mismatch"):
      mutation._instrument_source(source, [site])


class TestTestTargetOrdering(unittest.TestCase):
  # NOTE: our _build_core_tests keeps the FIRST implementation of each method
  # per module (duplicate method ids inside one module collapse). That is the
  # fork contract; the StarPilot original kept every implementation.
  CATALOG = {
    "test_one.py": ["m.A.test_rx", "m.B.test_rx", "m.A.test_tx"],
    "test_two.py": ["m.C.test_rx", "m.D.test_tx"],
  }

  def test_core_tests_dedupe_within_module_and_keep_across_modules(self):
    ordered = mutation._build_core_tests(self.CATALOG)
    # m.B.test_rx collapsed (same module+method as m.A.test_rx)
    self.assertEqual(Counter(ordered),
                     Counter({"m.A.test_rx": 1, "m.A.test_tx": 1, "m.C.test_rx": 1, "m.D.test_tx": 1}))
    self.assertNotIn("m.B.test_rx", ordered)

  def test_core_tests_order_widest_first_round_robin(self):
    ordered = mutation._build_core_tests(self.CATALOG)
    # test_rx implemented in 2 modules, test_tx in 2 -> rx module-first round robin
    self.assertEqual([t.rsplit(".", 1)[-1] for t in ordered[:2]], ["test_rx", "test_tx"])
    self.assertEqual(len(ordered), 4)

  def test_mode_file_maps_to_its_own_suite(self):
    toyota_site = _site(origin_file=Path("opendbc/safety/modes/toyota.h"))
    targets = mutation.build_priority_tests(toyota_site, {"test_toyota.py": ["t.T.test_tx"]}, ["core.test"])
    self.assertEqual(targets, ["t.T.test_tx"])

    core_site = _site(origin_file=Path("opendbc/safety/helpers.h"))
    self.assertEqual(mutation.build_priority_tests(core_site, {}, ["core.test"]), ["core.test"])


class TestEvalMutantOutcomes(unittest.TestCase):
  def test_failed_test_is_killed(self):
    site = _site()
    with patch.object(mutation, "run_unittest", return_value="t.T.test_tx"):
      result = mutation.eval_mutant(site, ["t.T.test_tx"], Path("unused.so"), False)
    self.assertEqual(result.outcome, "killed")

  def test_passing_test_is_survived(self):
    site = _site()
    with patch.object(mutation, "run_unittest", return_value=None):
      result = mutation.eval_mutant(site, ["t.T.test_tx"], Path("unused.so"), False)
    self.assertEqual(result.outcome, "survived")

  def test_infrastructure_exception_is_inf_error_not_kill(self):
    site = _site()
    with patch.object(mutation, "run_unittest", side_effect=RuntimeError("worker exploded")):
      result = mutation.eval_mutant(site, ["t.T.test_tx"], Path("unused.so"), False)
    self.assertEqual(result.outcome, "infra_error")
    self.assertIn("worker exploded", result.details)


def _tree_sitter_available() -> bool:
  import importlib.util
  return importlib.util.find_spec("tree_sitter") is not None and importlib.util.find_spec("tree_sitter_c") is not None


@unittest.skipIf(not (HAVE_CC and _tree_sitter_available()), "C toolchain or tree_sitter unavailable")
class TestEnumerateInstrumentCompileEndToEnd(unittest.TestCase):
  """Full pipeline on a minimal source with #line mapping back into SAFETY_DIR."""

  def test_enumerate_prunes_constant_context_and_compiles(self):
    mapped = mutation.SAFETY_DIR / "helpers.h"
    code = "\n".join((
      f'#line 1 "{mapped}"',
      'static const int limit = (4 > 2);',
      'int permit(int value) {',
      '  if (value > 3) { return 0; }',
      '  return value == 3;',
      '}',
      '',
    ))
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      original = root / "input.c"
      original.write_text(code)
      sites, counts, pruned, preprocessed = mutation.enumerate_sites(original, root / "input.i")
      self.assertTrue(sites)
      # site ids are dense: 0..n-1
      self.assertEqual({s.site_id for s in sites}, set(range(len(sites))))
      # the comparison inside the static file-scope initializer is pruned as
      # build-incompatible, and stays accounted for (not silently dropped)
      self.assertTrue(pruned)
      self.assertTrue(all(s.site_id in pruned for s in sites if s.origin_line == 1))
      executable = [s for s in sites if s.site_id not in pruned]
      self.assertTrue(executable)
      self.assertGreater(counts.get("comparison", 0) + counts.get("boundary", 0), 0)

      library = root / "mutated.so"
      mutation.compile_mutated_library(preprocessed, executable, library)
      native = ctypes.CDLL(str(library))
      native.permit.argtypes, native.permit.restype = [ctypes.c_int], ctypes.c_int
      native.mutation_set_active_mutant.argtypes = [ctypes.c_int]

      # inactive mutant: original semantics
      native.mutation_set_active_mutant(-1)
      self.assertEqual((native.permit(3), native.permit(4)), (1, 0))
      # activating the `value > 3` comparison flips the decision boundary
      target = next(s for s in executable if s.mutator == "comparison" and s.original_op == ">")
      native.mutation_set_active_mutant(target.site_id)
      self.assertEqual((native.permit(3), native.permit(4)), (0, 1))


class TestRunUnittestBaselineContract(unittest.TestCase):
  def test_baseline_smoke_uses_inactive_mutant(self):
    """run_unittest must set mutant_id=-1 (inactive) — a leaked active mutant
    would corrupt the baseline and turn every mutant into a false kill."""
    from opendbc.safety.tests.libsafety import libsafety_py
    safety = MagicMock()
    with patch.object(libsafety_py, "load"), patch.dict(libsafety_py.__dict__, {"libsafety": safety}):
      with patch("unittest.TextTestRunner.run", return_value=unittest.TestResult()):
        mutation.run_unittest(["t.T.test_tx"], Path("unused.so"), mutant_id=-1, verbose=False)
    safety.mutation_set_active_mutant.assert_called_once_with(-1)


if __name__ == "__main__":
  unittest.main()
