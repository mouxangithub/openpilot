"""Plugin hooks for chat and tool execution."""

from ai.hooks.registry import register_hook, run_hooks, clear_hooks

__all__ = ["register_hook", "run_hooks", "clear_hooks"]
