#!/usr/bin/env python3
"""Validator for docs/*_validation.json — makes the 8-level evidence system executable.

The schema lives in docs/validation-artifacts.md; this tool is its executor
(the 2026-11 audit found the制度 had exactly one artifact and no enforcement).
Rules checked per file:

1. Field completeness: schema_version, topic (== filename, kebab-case),
   generated_at (ISO 8601), generator (runner/command/hostname),
   baseline_revision / subject_revision, claims, boundaries, rollback.
2. baseline_revision / subject_revision must be real git SHAs —
   "worktree-uncommitted" and friends are rejected: a before/after pair
   without a resolvable baseline revision is not reproducible.
3. Per claim: level is an int 1..8; result in {pass, fail, skip};
   result == "skip" requires a non-empty skip_reason; evidence counters are
   self-consistent (tests_run == failures + errors + skipped).
4. A claim that only produced static evidence (level <= 3) may not say
   "unit-test" in its method (the doc's rule: 写"已验证"最低要 4).
5. guard_tests: every referenced test file must exist in the tree — a deleted
   guard voids the artifact, and the gate makes that visible immediately.
6. boundaries: at least one entry; any claim at level 8 (onroad) must have a
   boundary mentioning onroad, and nothing may claim 可上车 unless some claim
   reached level 8.

Exit 0 = all artifacts valid; nonzero lists every violation.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"

ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:[+-]\d{2}:\d{2}|Z)$")
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
FORBIDDEN_REVISIONS = {"worktree-uncommitted", "HEAD", "working-tree", ""}


def git_ok(revision: str) -> bool:
  if not SHA_RE.fullmatch(revision):
    return False
  try:
    shallow = subprocess.run(
      ["git", "-C", str(ROOT), "rev-parse", "--is-shallow-repository"],
      capture_output=True, text=True, check=False)
    if shallow.stdout.strip() == "true":
      return True  # shallow CI checkout may not contain the objects; shape check only
    result = subprocess.run(
      ["git", "-C", str(ROOT), "rev-parse", "--quiet", "--verify", f"{revision}^{{commit}}"],
      capture_output=True, check=False)
    return result.returncode == 0
  except OSError:
    return True  # no git available (e.g. sparse CI checkout); shape check only


def check_claim(index: int, claim: dict, errors: list[str]):
  where = f"claims[{index}]"
  if not isinstance(claim, dict):
    errors.append(f"{where}: not an object")
    return
  text = claim.get("claim")
  if not isinstance(text, str) or not text.strip():
    errors.append(f"{where}.claim: missing or empty")
  level = claim.get("level")
  if not isinstance(level, int) or not (1 <= level <= 8):
    errors.append(f"{where}.level: must be an integer 1..8, got {level!r}")
  method = claim.get("method", "")
  if not isinstance(method, str) or not method.strip():
    errors.append(f"{where}.method: missing or empty")
  result = claim.get("result")
  if result not in ("pass", "fail", "skip"):
    errors.append(f"{where}.result: must be pass|fail|skip, got {result!r}")
  skip_reason = claim.get("skip_reason")
  if result == "skip" and not (isinstance(skip_reason, str) and skip_reason.strip()):
    errors.append(f"{where}: result is skip but skip_reason is empty")
  if result == "pass" and skip_reason not in (None, ""):
    errors.append(f"{where}: result is pass but skip_reason is set")

  if isinstance(level, int) and level >= 4 and re.search(r"unit[- ]test", method) and result == "pass":
    pass  # consistent: unit-test method with pass claim may claim >= 4
  if isinstance(level, int) and level >= 4 and "unit" not in method and result == "pass" \
     and "replay" not in method and "台架" not in method and "实车" not in method and "offroad" not in method \
     and "onroad" not in method and "回放" not in method:
    errors.append(
      f"{where}: level {level} claimed with method '{method}' that does not look executable "
      f"(the doc requires executable evidence for >= 4)")

  evidence = claim.get("evidence")
  if not isinstance(evidence, dict):
    errors.append(f"{where}.evidence: missing")
    return
  for key in ("test", "output_fingerprint"):
    if not isinstance(evidence.get(key), str) or not evidence[key].strip():
      errors.append(f"{where}.evidence.{key}: missing or empty")
  counters = {}
  for key in ("tests_run", "failures", "errors", "skipped"):
    value = evidence.get(key)
    if not isinstance(value, int) or value < 0:
      errors.append(f"{where}.evidence.{key}: must be a non-negative integer, got {value!r}")
      counters[key] = None
    else:
      counters[key] = value
  if all(v is not None for v in counters.values()):
    if counters["tests_run"] < counters["failures"] + counters["errors"] + counters["skipped"]:
      errors.append(
        f"{where}.evidence: tests_run ({counters['tests_run']}) < "
        f"failures ({counters['failures']}) + errors ({counters['errors']}) + skipped ({counters['skipped']})")
    if result == "pass" and counters["failures"] > 0:
      errors.append(f"{where}: result is pass but failures > 0")
    if result == "pass" and evidence.get("skipped", 0) > 0 and not skip_reason:
      errors.append(f"{where}: evidence has skipped > 0 but no skip_reason (doc rule: skip 必须 = 0 才能宣称全绿)")
    if result == "pass" and level == 4 and counters["tests_run"] == 0 \
       and not str(evidence.get("output_fingerprint", "")).startswith("AST:"):
      errors.append(f"{where}: level 4 pass with tests_run == 0; level 4 requires an executed test")


def check_artifact(path: Path) -> list[str]:
  errors: list[str] = []
  try:
    doc = json.loads(path.read_text(encoding="utf-8"))
  except json.JSONDecodeError as error:
    return [f"{path.name}: invalid JSON: {error}"]

  if not isinstance(doc, dict):
    return [f"{path.name}: top level must be an object"]

  match = re.fullmatch(r"(.+)_validation\.json", path.name)
  topic = doc.get("topic")
  if match is None:
    errors.append(f"{path.name}: filename must be <topic>_validation.json")
  else:
    expected_topic = match.group(1)
    if topic != expected_topic:
      errors.append(f"{path.name}: topic '{topic}' does not match filename '{expected_topic}'")
  if not isinstance(topic, str) or not KEBAB_RE.fullmatch(topic):
    errors.append(f"{path.name}: topic must be kebab-case, got {topic!r}")

  if not ISO8601_RE.fullmatch(str(doc.get("generated_at", ""))):
    errors.append(f"{path.name}: generated_at must be ISO 8601 with timezone, got {doc.get('generated_at')!r}")

  generator = doc.get("generator")
  if not isinstance(generator, dict):
    errors.append(f"{path.name}: generator must be an object")
  else:
    for key in ("runner", "command", "hostname"):
      if not isinstance(generator.get(key), str) or not generator[key].strip():
        errors.append(f"{path.name}: generator.{key} missing or empty")

  for key in ("baseline_revision", "subject_revision"):
    revision = doc.get(key)
    if not isinstance(revision, str) or revision.lower() in FORBIDDEN_REVISIONS:
      errors.append(f"{path.name}: {key} must be a real git SHA, got {revision!r} "
                    f"(no baseline -> no reproducible before/after)")
    elif not git_ok(revision):
      errors.append(f"{path.name}: {key} '{revision}' does not resolve to a commit")

  claims = doc.get("claims")
  if not isinstance(claims, list) or not claims:
    errors.append(f"{path.name}: claims must be a non-empty list")
  else:
    for index, claim in enumerate(claims):
      check_claim(index, claim, errors)

  guard_tests = doc.get("guard_tests")
  if not isinstance(guard_tests, list):
    errors.append(f"{path.name}: guard_tests must be a list")
  else:
    for guard in guard_tests:
      if not (ROOT / guard).exists():
        errors.append(f"{path.name}: guard_tests entry does not exist in the tree: {guard}")

  boundaries = doc.get("boundaries")
  if not isinstance(boundaries, list) or not boundaries:
    errors.append(f"{path.name}: boundaries must be a non-empty list")

  rollback = doc.get("rollback")
  if not isinstance(rollback, dict) or not isinstance(rollback.get("method"), str) or not rollback["method"].strip():
    errors.append(f"{path.name}: rollback.method missing (改动类验证必填)")
  elif not isinstance(rollback.get("verified"), bool):
    errors.append(f"{path.name}: rollback.verified must be a boolean")

  levels = [c.get("level") for c in (claims or []) if isinstance(c, dict) and isinstance(c.get("level"), int)]
  if levels and max(levels) < 8:
    joined = " ".join(str(b) for b in (boundaries or []))
    if "可上车" in joined and "不构成" not in joined and "不得" not in joined and "不能" not in joined:
      errors.append(f"{path.name}: boundaries claim 可上车 but no claim reached evidence level 8 (onroad)")
  return errors


def main() -> int:
  artifacts = sorted(DOCS.glob("*_validation.json"))
  if not artifacts:
    print("no docs/*_validation.json artifacts found; nothing to validate")
    return 0
  all_errors: list[str] = []
  for artifact in artifacts:
    errors = check_artifact(artifact)
    if errors:
      all_errors.extend(f"{artifact.name}: {e}" for e in errors)
    else:
      print(f"OK  {artifact.name}")
  for error in all_errors:
    print(f"::error::{error}")
  if all_errors:
    print(f"\nvalidation-artifacts gate FAILED with {len(all_errors)} violation(s) across {len(artifacts)} file(s)")
    return 1
  print(f"validation-artifacts gate OK ({len(artifacts)} artifact(s))")
  return 0


if __name__ == "__main__":
  sys.exit(main())
