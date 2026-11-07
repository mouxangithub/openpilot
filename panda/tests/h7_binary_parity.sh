#!/usr/bin/env bash
# Proves a change does not alter the H7 firmware, so F4/dos work can never
# silently change the H7 build. Compares HEAD against a base ref:
#   $1  base ref (default: merge-base with origin/master)
# CI passes the PR base (pull_request) or the previous tip (push), because
# long-lived F4 branches intentionally change shared code vs upstream master.
# Exits nonzero on any difference.
#
# The unsigned images are compared, not the .signed ones: the signature covers
# the baked-in git version, so two otherwise identical trees never sign the
# same. The version string itself is scrubbed before hashing; it is metadata,
# not code, and the fixed-length replacement keeps every other byte aligned.
set -euo pipefail

cd "$(dirname "$0")/.."

BASE_REF="${1:-}"
if [ -z "$BASE_REF" ]; then
  git fetch -q origin master
  BASE_REF=$(git merge-base HEAD origin/master)
fi

TARGETS="panda_h7 body_h7 panda_jungle_h7"

hash_tree() {
  scons -Q -j"$(nproc 2>/dev/null || sysctl -n hw.ncpu)" >/dev/null
  for t in $TARGETS; do
    for f in "board/obj/$t/main.bin" "board/obj/bootstub.$t.bin"; do
      python3 - "$f" <<'PY'
import hashlib, re, sys
dat = open(sys.argv[1], "rb").read()
dat = re.sub(rb"DEV-[^-\x00]{1,10}-(DEBUG|RELEASE)", lambda m: b"DEV-" + b"X" * (len(m.group(0)) - 4 - len(m.group(1)) - 1) + b"-" + m.group(1), dat)
print(hashlib.sha256(dat).hexdigest(), sys.argv[1])
PY
    done
  done
}

CUR=$(mktemp)
BASE=$(mktemp)
WT=$(mktemp -d)
trap 'git worktree remove -f "$WT" 2>/dev/null || true; rm -f "$CUR" "$BASE"' EXIT

hash_tree > "$CUR"
git worktree add -q --detach "$WT" "$BASE_REF"
( cd "$WT" && hash_tree ) > "$BASE"

if diff -u "$BASE" "$CUR"; then
  echo "H7 binary parity vs $BASE_REF: PASS"
else
  echo "H7 binary parity vs $BASE_REF: FAIL, H7 images changed"
  exit 1
fi
