"""Spill waterfall: post-execute externalization for large tool results."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_EXTERNALIZE_THRESHOLD = 51200
DEFAULT_HEAD_CHARS = 2000
DEFAULT_TAIL_CHARS = 2000


class SpillWaterfall:
    """Externalize oversized plain-text results, return preview + locator."""

    def __init__(self, cwd: str, threshold: int = DEFAULT_EXTERNALIZE_THRESHOLD) -> None:
        self.cwd = Path(cwd)
        self.threshold = threshold
        self.spill_dir = self.cwd / ".ai" / "spill"
        self.spill_dir.mkdir(parents=True, exist_ok=True)

    def process(self, result: dict[str, Any], *, tool_name: str = "", call_id: str = "") -> dict[str, Any]:
        if not isinstance(result, dict):
            return result
        content = result.get("content")
        if not isinstance(content, str):
            return result
        if len(content) <= self.threshold:
            return result
        return self._externalize(content, tool_name=tool_name, call_id=call_id, original=result)

    def _externalize(self, content: str, *, tool_name: str, call_id: str, original: dict[str, Any]) -> dict[str, Any]:
        file_name = f"{tool_name}_{call_id}.txt".replace("/", "_").replace("\\", "_")
        path = self.spill_dir / file_name
        path.write_text(content, encoding="utf-8")
        head = content[:DEFAULT_HEAD_CHARS]
        tail = content[-DEFAULT_TAIL_CHARS:] if len(content) > DEFAULT_HEAD_CHARS + DEFAULT_TAIL_CHARS else ""
        preview = head
        if tail:
            preview += f"\n…[{len(content) - DEFAULT_HEAD_CHARS - DEFAULT_TAIL_CHARS} chars omitted]…\n" + tail
        out = dict(original)
        out["content"] = preview + f"\n[full at: {path}]"
        out["externalized"] = True
        out["spill_path"] = str(path)
        return out

    def spill_text_if_needed(
        self,
        text: str,
        *,
        session_id: str,
        tool_name: str,
        call_id: str,
        params: Any = None,
        kind: str = "dispatch",
    ) -> tuple[str | None, str]:
        if len(text) <= self.threshold:
            return None, ""
        file_name = f"{kind}_{session_id}_{tool_name}_{call_id}.txt".replace("/", "_").replace("\\", "_")
        path = self.spill_dir / file_name
        path.write_text(text, encoding="utf-8")
        head = text[:DEFAULT_HEAD_CHARS]
        tail = text[-DEFAULT_TAIL_CHARS:] if len(text) > DEFAULT_HEAD_CHARS + DEFAULT_TAIL_CHARS else ""
        preview = head
        if tail:
            preview += f"\n…[{len(text) - DEFAULT_HEAD_CHARS - DEFAULT_TAIL_CHARS} chars omitted]…\n" + tail
        return preview + f"\n[full at: {path}]", str(path)
