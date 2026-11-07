"""Clean duplicated sections in server/handlers/api.py."""
from pathlib import Path

path = Path(__file__).resolve().parent.parent / "server" / "handlers" / "api.py"
lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

# Remove duplicate block: second _scheduler_execute_action through second api_chat_job_detail
start = None
end = None
seen_chat = 0
for i, line in enumerate(lines):
  if line.startswith("async def _scheduler_execute_action"):
    if start is None:
      start = i  # first occurrence - keep
    else:
      dup_start = i
      # find api_shell after duplicate chat block
      for j in range(i, len(lines)):
        if lines[j].startswith("async def api_shell"):
          end = j
          break
      if end:
        lines = lines[:dup_start] + lines[end:]
      break

path.write_text("".join(lines), encoding="utf-8")
print(f"cleaned {path}, lines={len(lines)}")
