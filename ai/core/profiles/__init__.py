"""Unified profile / preset system for op助手."""

from __future__ import annotations

from ai.core.profiles.profile import Profile, ProfileDomain
from ai.core.profiles.store import ProfileStore
from ai.core.profiles.manager import ProfileManager

__all__ = ["Profile", "ProfileDomain", "ProfileStore", "ProfileManager"]
