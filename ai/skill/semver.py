"""Internal semver comparison with constraint satisfaction.

Zero-dependency implementation covering standard semantic versioning:
  - parse: "1.2.3", "1.2.3-alpha", "1.2.3-alpha.1+build"
  - compare: 1.2.0 < 1.10.0 < 2.0.0-alpha < 2.0.0
  - satisfies: =x.y.z, >=x.y.z, <=x.y.z, >x.y.z, <x.y.z, ^x.y.z, ~x.y.z
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_SEMVER_RE = re.compile(
  r"^(?P<major>0|[1-9]\d*)\."
  r"(?P<minor>0|[1-9]\d*)\."
  r"(?P<patch>0|[1-9]\d*)"
  r"(?:-(?P<prerelease>[a-zA-Z0-9.\-]+))?"
  r"(?:\+(?P<build>[a-zA-Z0-9.\-]+))?$"
)


@dataclass(frozen=True)
class Semver:
  """Parsed semantic version value object."""

  major: int
  minor: int
  patch: int
  prerelease: str = ""
  build: str = ""
  raw: str = ""

  @staticmethod
  def parse(version: str) -> "Semver":
    """Parse a semver string."""
    text = str(version or "").strip()
    if text.startswith("v") or text.startswith("V"):
      text = text[1:]
    match = _SEMVER_RE.match(text)
    if not match:
      raise ValueError(f"invalid semver: {version!r}")
    groups = match.groupdict()
    return Semver(
      major=int(groups["major"]),
      minor=int(groups["minor"]),
      patch=int(groups["patch"]),
      prerelease=groups.get("prerelease") or "",
      build=groups.get("build") or "",
      raw=text,
    )

  @staticmethod
  def from_string(version: str) -> "Semver":
    """Alias for parse; returns a zeroed version on failure (best-effort)."""
    try:
      return Semver.parse(version)
    except Exception:
      return Semver(major=0, minor=0, patch=0, raw=str(version or ""))

  def __str__(self) -> str:
    if self.raw:
      return self.raw
    out = f"{self.major}.{self.minor}.{self.patch}"
    if self.prerelease:
      out += f"-{self.prerelease}"
    if self.build:
      out += f"+{self.build}"
    return out

  def _numeric_tuple(self) -> tuple[int, int, int]:
    return (self.major, self.minor, self.patch)

  def _prerelease_parts(self) -> list[str | int]:
    """Split prerelease identifier for precedence comparison."""
    if not self.prerelease:
      return []
    parts: list[str | int] = []
    for part in self.prerelease.split("."):
      part = part.strip()
      if part.isdigit():
        parts.append(int(part))
      else:
        parts.append(part)
    return parts

  def compare(self, other: Any) -> int:
    """Return -1/0/1 like standard semver precedence."""
    if isinstance(other, str):
      other = Semver.parse(other)
    if not isinstance(other, Semver):
      raise TypeError(f"cannot compare Semver with {type(other)}")
    if self._numeric_tuple() != other._numeric_tuple():
      return -1 if self._numeric_tuple() < other._numeric_tuple() else 1
    left = self._prerelease_parts()
    right = other._prerelease_parts()
    if left == right:
      return 0
    if not left:
      return 1
    if not right:
      return -1
    for a, b in zip(left, right):
      if a == b:
        continue
      if isinstance(a, int) and isinstance(b, int):
        return -1 if a < b else 1
      if isinstance(a, int):
        return -1
      if isinstance(b, int):
        return 1
      return -1 if a < b else 1
    return -1 if len(left) < len(right) else 1

  def __lt__(self, other: Any) -> bool:
    return self.compare(other) < 0

  def __le__(self, other: Any) -> bool:
    return self.compare(other) <= 0

  def __gt__(self, other: Any) -> bool:
    return self.compare(other) > 0

  def __ge__(self, other: Any) -> bool:
    return self.compare(other) >= 0

  def __eq__(self, other: Any) -> bool:
    if isinstance(other, str):
      try:
        other = Semver.parse(other)
      except Exception:
        return False
    if not isinstance(other, Semver):
      return NotImplemented
    return self.compare(other) == 0

  def __hash__(self) -> int:
    return hash((self.major, self.minor, self.patch, self.prerelease))

  def satisfies(self, constraint: str) -> bool:
    """Check whether this version satisfies a constraint string.

    Supported operators:
      =1.2.3        exact
      >=1.2.3       greater-or-equal
      <=1.2.3       less-or-equal
      >1.2.3        greater
      <1.2.3        less
      ^1.2.3        compatible with (same major, >= version)
      ~1.2.3        approximately equivalent to (same major.minor, >= version)
    """
    text = str(constraint or "").strip()
    if not text:
      return False

    operators = [">=", "<=", ">", "<", "^", "~", "="]
    op = "="
    for candidate in operators:
      if text.startswith(candidate):
        op = candidate
        text = text[len(candidate):].strip()
        break

    if op in ("^", "~"):
      try:
        target = Semver.parse(text)
      except Exception:
        return False
      if self < target:
        return False
      if op == "^":
        return self.major == target.major
      return self.major == target.major and self.minor == target.minor

    try:
      target = Semver.parse(text)
    except Exception:
      return False

    if op == "=":
      return self == target
    if op == ">=":
      return self >= target
    if op == "<=":
      return self <= target
    if op == ">":
      return self > target
    if op == "<":
      return self < target
    return False
