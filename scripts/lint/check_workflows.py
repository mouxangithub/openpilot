#!/usr/bin/env python3
"""CI workflow sanity gate.

Two layers:
1. actionlint (pinned release, checksum-verified) for workflow syntax and
   expression semantics. Skipped with a warning on platforms without a pinned
   checksum so local linting still works.
2. Referenced-file existence: every repo-relative script invoked from a
   workflow `run:` block must exist in the tree. This is the gate that would
   have caught upstream-sync.yml referencing nine .github/scripts/*.sh files
   that never existed (2026-11 audit finding).
"""
import hashlib
import io
import json
import os
import platform
import re
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = "1.7.12"
ARCHIVE_SHA256 = {
  "darwin_amd64": "5b44c3bc2255115c9b69e30efc0fecdf498fdb63c5d58e17084fd5f16324c644",
  "darwin_arm64": "aba9ced2dee8d27fecca3dc7feb1a7f9a52caefa1eb46f3271ea66b6e0e6953f",
  "linux_amd64": "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8",
  "linux_arm64": "325e971b6ba9bfa504672e29be93c24981eeb1c07576d730e9f7c8805afff0c6",
}
SCRIPT_TOKEN_RE = re.compile(r"(?<![\w./-])((?:\./)?[A-Za-z0-9_.][\w.-]*(?:/[\w.-]+)+\.(?:sh|py|bash))(?![\w-])")
TOKEN_DENYLIST = ("node_modules/", ".cache/", "http://", "https://")
# interpreter keywords after which a repo-relative script path is expected to exist
INTERPRETER_RE = re.compile(r"(?:^|[\s;&|(])(?:bash|sh|zsh|source|python3?|python3\.\d+|exec)\s+(?:[-+]@\S+\s+|--\S+\s+|-\S+\s+)*$")


def actionlint() -> Path | None:
  machine = {"x86_64": "amd64", "aarch64": "arm64", "AMD64": "amd64", "arm64": "arm64"}.get(platform.machine(), platform.machine())
  target = f"{platform.system().lower()}_{machine}"
  if target not in ARCHIVE_SHA256:
    print(f"::warning::no pinned actionlint checksum for {target}; skipping actionlint layer")
    return None
  cache = ROOT / ".cache" / f"actionlint-{VERSION}-{target}"
  archive = cache / "release.tar.gz"
  binary = cache / "actionlint.exe" if platform.system() == "Windows" else cache / "actionlint"
  cache.mkdir(parents=True, exist_ok=True)
  try:
    if not archive.exists():
      url = f"https://github.com/rhysd/actionlint/releases/download/v{VERSION}/actionlint_{VERSION}_{target}.tar.gz"
      with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read()
      if hashlib.sha256(data).hexdigest() != ARCHIVE_SHA256[target]:
        raise RuntimeError("actionlint release checksum mismatch")
      with tempfile.NamedTemporaryFile(dir=cache, delete=False) as temporary:
        temporary.write(data)
        name = temporary.name
      os.replace(name, archive)
    data = archive.read_bytes()
    if hashlib.sha256(data).hexdigest() != ARCHIVE_SHA256[target]:
      raise RuntimeError("Cached actionlint release checksum mismatch")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as release:
      member = release.extractfile("actionlint.exe" if platform.system() == "Windows" else "actionlint")
      if member is None:
        raise RuntimeError("actionlint release has no binary")
      expected = member.read()
    if not binary.exists() or binary.read_bytes() != expected:
      with tempfile.NamedTemporaryFile(dir=cache, delete=False) as temporary:
        temporary.write(expected)
        name = temporary.name
      os.chmod(name, 0o755)
      os.replace(name, binary)
    return binary
  except (OSError, RuntimeError) as error:
    print(f"::warning::actionlint unavailable ({error}); skipping actionlint layer")
    return None


def run_actionlint(binary: Path, workflows: list[str]) -> bool:
  result = subprocess.run([str(binary), "-shellcheck=", "-pyflakes=", "-format", "{{json .}}", *workflows],
                          cwd=ROOT, text=True, capture_output=True)
  if result.returncode not in (0, 1) or result.stderr:
    print(result.stderr or result.stdout or f"actionlint exited {result.returncode}", file=sys.stderr)
    return False
  errors = json.loads(result.stdout or "[]")
  failed = False
  for error in errors:
    # jobs disabled via `if: false` carry an explicit maintenance comment; the
    # constant-false diagnostic is style, not breakage.
    if error["kind"] == "if-cond" and 'constant expression "false" in condition' in error["message"]:
      continue
    print(f'{error["filepath"]}:{error["line"]}:{error["column"]}: {error["message"]}')
    failed = True
  return failed


def extract_run_blocks(text: str) -> list[tuple[str, int]]:
  """Collect every `run:` value as (block_text, zero-based start line)."""
  lines = text.splitlines()
  blocks: list[tuple[str, int]] = []
  i = 0
  while i < len(lines):
    line = lines[i]
    stripped = line.strip()
    if stripped.startswith("- "):
      stripped = stripped[2:].lstrip()
    if stripped.startswith("run:"):
      value = stripped[4:].strip()
      if value in ("|", ">|", "|-", ">-", "|+", ">+", ">", "|2"):
        base_indent = len(line) - len(line.lstrip())
        i += 1
        start = i
        collected: list[str] = []
        while i < len(lines):
          candidate = lines[i]
          if candidate.strip() == "" or len(candidate) - len(candidate.lstrip()) > base_indent:
            collected.append(candidate)
            i += 1
          else:
            break
        blocks.append(("\n".join(collected), start))
        continue
      elif value:
        blocks.append((value, i))
    i += 1
  return blocks


def is_command_position(prefix: str) -> bool:
  """True if the text immediately before a token is a command position."""
  if prefix == "" or prefix.endswith("\n") or prefix.isspace():
    return True  # start of line (incl. YAML block continuation lines)
  if INTERPRETER_RE.search(prefix[-60:]):
    return True
  stripped = prefix[-10:].rstrip()
  if stripped.endswith((";", "&&", "||", "|", "(", "`", "$(")):
    return True
  return False


def check_referenced_files(workflow_path: Path) -> bool:
  raw = workflow_path.read_text(encoding="utf-8")
  failed = False
  seen = set()
  for block, start_line in extract_run_blocks(raw):
    # drop comment lines inside run blocks
    block = "\n".join(l for l in block.splitlines() if not l.lstrip().startswith("#"))
    for match in SCRIPT_TOKEN_RE.finditer(block):
      token = match.group(1)
      if token.startswith("./"):
        token = token[2:]  # strip only the explicit "./" prefix, keep leading dots like .github/
      if token in seen or any(d in token for d in TOKEN_DENYLIST):
        continue
      # `git ... -- path` file arguments and generated outputs are not repo scripts
      if not is_command_position(block[:match.start()]):
        continue
      seen.add(token)
      if (ROOT / token).exists():
        continue
      line_no = start_line + block[:match.start()].count("\n") + 1
      print(f'{workflow_path.relative_to(ROOT)}:{line_no}: referenced file does not exist: {token}')
      failed = True
  return failed


def main() -> int:
  if sys.argv[1:] == ["--install"]:
    binary = actionlint()
    return 0 if binary is not None else 1
  workflows = sorted(str(p.relative_to(ROOT)) for p in (ROOT / ".github/workflows").glob("*.yaml"))
  workflows += sorted(str(p.relative_to(ROOT)) for p in (ROOT / ".github/workflows").glob("*.yml"))
  if not workflows:
    print("No workflows found", file=sys.stderr)
    return 1

  failed = False
  binary = actionlint()
  if binary is not None:
    failed = run_actionlint(binary, workflows) or failed
  for workflow in workflows:
    failed = check_referenced_files(ROOT / workflow) or failed
  return int(failed)


if __name__ == "__main__":
  try:
    sys.exit(main())
  except (OSError, RuntimeError, ValueError) as error:
    print(error, file=sys.stderr)
    sys.exit(1)
