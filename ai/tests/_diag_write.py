"""Diagnostic script to verify file writing works."""
from pathlib import Path

out = Path(__file__).with_suffix(".marker")
out.write_text("marker_written", encoding="utf-8")
