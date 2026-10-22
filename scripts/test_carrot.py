#!/usr/bin/env python3
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Run the carrot suite and refuse to pass with tests skipped inside it.

A `try/except ImportError` or `skipUnless` gate with a typo in it skips silently,
and a green line that skipped 11 tests reads exactly like a green line that ran
them - which is how a whole planner's tests went unrun for a while (the class is
`CarrotPlanner`, not `CarrotPilot`). This runner makes the skips visible and
fatal, so the person who adds a gate has to write down why it can skip.

  * every skip is printed with its test id and reason, and fails the run, unless
    its id is in the `skips` list of `--allow-from FILE` (a JSON array of exact
    test ids, each with a reason - a skip that cannot be explained should not
    exist);
  * failures and errors are printed and fail the run, independently; pass
    `--allow-from` with a `failures` list to gate on a machine with known
    environment gaps (a device without CANPacker, say) without letting skips
    back in;
  * `--list-only` prints the skips and exits 0, for taking a baseline.

Run:  python3 scripts/test_carrot.py [--allow-from FILE] [--list-only]
"""
import argparse
import json
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
START = os.path.join(REPO, 'openpilot', 'sunnypilot', 'carrot')


def _ids(runs) -> list[str]:
  return sorted(f'{test.id()}' for test, _ in runs)


def run_suite() -> unittest.TestResult:
  suite = unittest.defaultTestLoader.discover(START, top_level_dir=REPO)
  result = unittest.TextTestRunner(verbosity=1).run(suite)
  return result


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument('--allow-from', help='JSON file: {"skips": [{"id": ..., "reason": ...}], "failures": [...]}')
  parser.add_argument('--list-only', action='store_true', help='print the skips and exit 0')
  args = parser.parse_args()

  allowed_skips: set[str] = set()
  allowed_failures: set[str] = set()
  if args.allow_from:
    with open(args.allow_from, encoding='utf-8') as f:
      entries = json.load(f)
    allowed_skips = {e['id'] for e in entries.get('skips', [])}
    allowed_failures = {e['id'] for e in entries.get('failures', [])}

  result = run_suite()
  skipped = result.skipped
  failed = [case for case, _ in result.failures] + [case for case, _ in result.errors]

  print()
  print(f'== {result.testsRun} run, {len(failed)} failed, {len(skipped)} skipped ==')

  unexpected_skips = [i for i in _ids(skipped) if i not in allowed_skips]
  unexpected_failures = [c.id() for c in failed if c.id() not in allowed_failures]

  if skipped:
    print('\nskipped (id — reason):')
    for test, reason in skipped:
      mark = '' if test.id() in allowed_skips else '  <-- NOT ALLOWED'
      print(f'  {test.id()} — {reason or "no reason"}{mark}')
  if unexpected_failures:
    print('\nfailed (not in the allowlist):')
    for i in unexpected_failures:
      print(f'  {i}')

  if args.list_only:
    return 0

  # A skip that is not on the allowlist is the defect this runner exists for:
  # it fails the run even when everything that did run passed.
  return 1 if (unexpected_skips or unexpected_failures) else 0


if __name__ == '__main__':
  sys.exit(main())
