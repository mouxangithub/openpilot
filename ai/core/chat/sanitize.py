"""Strip tool-call syntax leaked into model content (e.g. Kimi code models)."""

from __future__ import annotations

import re

# functions.tool_name: {...} or functions.tool_name: "..." with optional [N] badge
_FN_LEAK = re.compile(
    r"(?:^|\s)functions\.([a-zA-Z_][\w.]*)\s*:\s*"
    r"(?:\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\}|\"[^\"]*\"|'[^']*'|[^\s\[]+)"
    r"(?:\s*\[\d+\])?",
    re.MULTILINE,
)


def strip_leaked_tool_calls(text: str | None) -> str:
    """Remove function-call text that some models emit in content instead of tool_calls."""
    if not text:
        return ""
    cleaned = _FN_LEAK.sub(" ", text)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
