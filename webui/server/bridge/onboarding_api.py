"""Onboarding status — terms, sunnylink consent, training (mirrors layouts/onboarding.py)."""

from __future__ import annotations

from typing import Any


def _terms_version() -> str:
  try:
    from openpilot.common.version import terms_version
    return terms_version
  except Exception:
    return "2"


def _terms_version_sp() -> str:
  try:
    from openpilot.common.version import terms_version_sp
    return terms_version_sp
  except Exception:
    return "1.0"


def _training_version() -> str:
  try:
    from openpilot.common.version import training_version
    return training_version
  except Exception:
    return "0.2.0"


def _sunnylink_consent_version() -> str:
  try:
    from openpilot.common.version import sunnylink_consent_version
    return sunnylink_consent_version
  except Exception:
    return "1.0"


def _sunnylink_consent_declined() -> str:
  try:
    from openpilot.common.version import sunnylink_consent_declined
    return sunnylink_consent_declined
  except Exception:
    return "-1"


def _params():
  from openpilot.common.params import Params
  return Params()


def _sunnylink_consent_ok(p) -> bool:
  consent = p.get("CompletedSunnylinkConsentVersion")
  return consent in {_sunnylink_consent_version(), _sunnylink_consent_declined()}


def onboarding_status() -> dict[str, Any]:
  try:
    p = _params()
    terms_version = _terms_version()
    terms_version_sp = _terms_version_sp()
    training_version = _training_version()
    sunnylink_version = _sunnylink_consent_version()
    sunnylink_declined = _sunnylink_consent_declined()

    terms_ok = (
      p.get("HasAcceptedTerms") == terms_version
      and p.get("HasAcceptedTermsSP") == terms_version_sp
    )
    sunnylink_ok = _sunnylink_consent_ok(p)
    training_ok = p.get("CompletedTrainingVersion") == training_version
    completed = terms_ok and sunnylink_ok and training_ok

    phase = "terms"
    if terms_ok and not sunnylink_ok:
      phase = "sunnylink"
    elif terms_ok and sunnylink_ok and not training_ok:
      phase = "training"
    elif completed:
      phase = "done"

    return {
      "ok": True,
      "completed": completed,
      "terms_accepted": terms_ok,
      "sunnylink_consent_done": sunnylink_ok,
      "training_completed": training_ok,
      "phase": phase,
      "terms_version": terms_version,
      "terms_version_sp": terms_version_sp,
      "training_version": training_version,
      "sunnylink_consent_version": sunnylink_version,
      "sunnylink_consent_declined": sunnylink_declined,
      "sunnylink_enabled": p.get_bool("SunnylinkEnabled"),
    }
  except Exception as exc:
    return {"ok": False, "error": str(exc), "completed": True}


def accept_terms() -> dict[str, Any]:
  try:
    p = _params()
    p.put("HasAcceptedTerms", _terms_version())
    p.put("HasAcceptedTermsSP", _terms_version_sp())
    return onboarding_status()
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def accept_sunnylink_consent(accept: bool = True) -> dict[str, Any]:
  try:
    p = _params()
    if accept:
      p.put("CompletedSunnylinkConsentVersion", _sunnylink_consent_version())
      p.put_bool("SunnylinkEnabled", True)
    else:
      p.put("CompletedSunnylinkConsentVersion", _sunnylink_consent_declined())
      p.put_bool("SunnylinkEnabled", False)
    return onboarding_status()
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def complete_training() -> dict[str, Any]:
  try:
    p = _params()
    p.put("CompletedTrainingVersion", _training_version())
    p.put_bool("IsDriverViewEnabled", False)
    return onboarding_status()
  except Exception as exc:
    return {"ok": False, "error": str(exc)}
