"""Command safety classifier for shell/system commands.

Adds learn-workbuddy-style safety tiers on top of the existing sandbox policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class SafetyTier(StrEnum):
  SAFE = "safe"
  CAUTION = "caution"
  HIGH_RISK = "high_risk"
  DESTRUCTIVE = "destructive"
  BLOCKED = "blocked"


@dataclass(frozen=True)
class CommandClassification:
  tier: SafetyTier
  reason: str
  blocked: bool = False


class CommandSafetyClassifier:
  """Classify shell commands by safety tier."""

  BLOCKED_PATTERNS: tuple[str, ...] = (
    "mkfs", "dd if=/dev/zero", "rm -rf /", "rm -rf /*", ":(){ :|:& };:",
    "shutdown", "reboot", "poweroff", "halt",
  )

  DESTRUCTIVE_PATTERNS: tuple[str, ...] = (
    "rm -rf", "rm -r", "rm -f", "del /s", "rmdir /s",
  )

  HIGH_RISK_PATTERNS: tuple[str, ...] = (
    "sudo", "su -", "chmod 777", "chown -R root", "passwd",
    "fdisk", "parted", "mkfs.",
  )

  CAUTION_PATTERNS: tuple[str, ...] = (
    "curl", "wget", "pip install", "npm install", "git push", "git reset --hard",
  )

  def classify(self, command: str) -> CommandClassification:
    lowered = command.lower().strip()
    for pat in self.BLOCKED_PATTERNS:
      if pat in lowered:
        return CommandClassification(SafetyTier.BLOCKED, f"blocked pattern: {pat}", blocked=True)
    for pat in self.DESTRUCTIVE_PATTERNS:
      if lowered.startswith(pat) or f" {pat}" in lowered:
        return CommandClassification(SafetyTier.DESTRUCTIVE, f"destructive pattern: {pat}")
    for pat in self.HIGH_RISK_PATTERNS:
      if pat in lowered:
        return CommandClassification(SafetyTier.HIGH_RISK, f"high-risk pattern: {pat}")
    for pat in self.CAUTION_PATTERNS:
      if pat in lowered:
        return CommandClassification(SafetyTier.CAUTION, f"caution pattern: {pat}")
    return CommandClassification(SafetyTier.SAFE, "no dangerous patterns detected")

  def check(self, command: str, policy_mode: str = "read-only") -> dict[str, Any]:
    classification = self.classify(command)
    allowed = not classification.blocked
    if policy_mode == "read-only" and classification.tier not in (SafetyTier.SAFE,):
      allowed = False
    return {
      "allowed": allowed,
      "tier": classification.tier.value,
      "reason": classification.reason,
      "blocked": classification.blocked,
    }
