#!/usr/bin/env bash
# Push OUTPUT_BRANCH (current HEAD) to origin. Auth: SYNC_PAT > GITHUB_TOKEN.
set -euo pipefail

OUTPUT_BRANCH="${OUTPUT_BRANCH:?OUTPUT_BRANCH not set}"
REMOTE_URL="$(git remote get-url origin)"

if [ -n "${SYNC_PAT:-}" ]; then
  # https://github.com/owner/repo.git -> https://x-access-token:<pat>@github.com/owner/repo.git
  AUTH_URL="$(python - "${REMOTE_URL}" "${SYNC_PAT}" <<'PYEOF'
import sys
from urllib.parse import urlsplit, urlunsplit
url, token = sys.argv[1], sys.argv[2]
parts = urlsplit(url)
netloc = f"x-access-token:{token}@{parts.netloc}"
print(urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment)))
PYEOF
)"
else
  AUTH_URL="${REMOTE_URL}"
fi

for i in 1 2 3; do
  if git push "${AUTH_URL}" "HEAD:refs/heads/${OUTPUT_BRANCH}"; then
    echo "Pushed ${OUTPUT_BRANCH}"
    exit 0
  fi
  echo "Push attempt ${i} failed; retrying after fetch"
  git fetch origin "${OUTPUT_BRANCH}" 2>/dev/null || true
  sleep 5
done
echo "::error::Failed to push ${OUTPUT_BRANCH} after 3 attempts"
exit 1
