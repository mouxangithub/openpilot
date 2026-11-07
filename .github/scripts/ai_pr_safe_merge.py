#!/usr/bin/env python3
"""Rules-based safe squash merge for PRs labeled `ai-safe-merge`.

Gate order (all must pass, anything ambiguous fails closed):
1. PR has `ai-safe-merge` label and NOT `upstream-sync`.
2. PR head is from the same repository (no fork heads).
3. GitHub reports the PR as mergeable with a clean/blocking-free merge state.
4. Every commit status and check run on the head SHA is success/neutral/skipped.
5. No outstanding CHANGES_REQUESTED review.
Only then: squash-merge via the API using the PR title.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"
REQUIRED_LABEL = "ai-safe-merge"
BLOCKING_LABEL = "upstream-sync"
WAIT_FOR_CHECKS_SECONDS = 300


def api(method: str, path: str, token: str, payload: dict | None = None) -> tuple[int, dict | list]:
  request = urllib.request.Request(
    f"{API}{path}", method=method,
    data=json.dumps(payload).encode() if payload is not None else None,
    headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
  try:
    with urllib.request.urlopen(request, timeout=30) as response:
      return response.status, json.loads(response.read() or b"{}")
  except urllib.error.HTTPError as error:
    return error.code, json.loads(error.read() or b"{}")


def event_pull_number() -> int:
  event = json.load(open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8"))
  return int(event["pull_request"]["number"])


def main() -> int:
  token = os.environ.get("GITHUB_TOKEN", "")
  repo = os.environ["GITHUB_REPOSITORY"]
  pr_number = event_pull_number()

  status, pr = api("GET", f"/repos/{repo}/pulls/{pr_number}", token)
  if status != 200:
    print(f"PR fetch failed: {status} {pr}")
    return 1

  labels = {label["name"] for label in pr.get("labels", [])}
  if REQUIRED_LABEL not in labels:
    print(f"Label '{REQUIRED_LABEL}' absent; nothing to do.")
    return 0
  if BLOCKING_LABEL in labels:
    print(f"Blocking label '{BLOCKING_LABEL}' present; refusing to merge.")
    return 1
  if pr["head"]["repo"]["full_name"] != repo:
    print("Head is from a different repository; refusing.")
    return 1

  # wait (bounded) for GitHub to compute mergeability
  for _ in range(30):
    if pr.get("mergeable") is not None:
      break
    time.sleep(10)
    _, pr = api("GET", f"/repos/{repo}/pulls/{pr_number}", token)
  if not pr.get("mergeable"):
    print(f"PR not mergeable (mergeable={pr.get('mergeable')}, state={pr.get('mergeable_state')}).")
    return 1
  if pr.get("mergeable_state") in ("dirty", "unstable", "blocked") and pr["mergeable_state"] != "blocked":
    print(f"mergeable_state={pr['mergeable_state']}; refusing.")
    return 1

  head_sha = pr["head"]["sha"]

  # commit statuses: any state != success fails (pending handled by bounded wait)
  deadline = time.monotonic() + WAIT_FOR_CHECKS_SECONDS
  while True:
    _, combined = api("GET", f"/repos/{repo}/commits/{head_sha}/status", token)
    bad = [s for s in combined.get("statuses", []) if s["state"] not in ("success", "")]
    if not bad:
      break
    if any(s["state"] == "failure" for s in bad):
      for s in bad:
        print(f"status failed: {s['context']}: {s['state']}")
      return 1
    if time.monotonic() > deadline:
      for s in bad:
        print(f"status pending past deadline: {s['context']}: {s['state']}")
      return 1
    time.sleep(20)

  # check runs: success/neutral/skipped allowed; pending waited; failure fails
  while True:
    _, runs = api("GET", f"/repos/{repo}/commits/{head_sha}/check-runs", token)
    bad = [r for r in runs.get("check_runs", []) if r["conclusion"] not in ("success", "neutral", "skipped", None)]
    if not bad:
      pending = [r for r in runs.get("check_runs", []) if r["conclusion"] is None and r["status"] != "completed"]
      if not pending or time.monotonic() > deadline:
        break
      time.sleep(20)
      continue
    for r in bad:
      print(f"check run failed: {r['name']}: {r['conclusion']}")
    return 1

  # reviews: outstanding CHANGES_REQUESTED blocks
  _, reviews = api("GET", f"/repos/{repo}/pulls/{pr_number}/reviews", token)
  latest: dict[str, str] = {}
  for review in reviews:
    if review["user"] and review["state"] in ("APPROVED", "CHANGES_REQUESTED"):
      latest[review["user"]["login"]] = review["state"]
  blockers = [user for user, state in latest.items() if state == "CHANGES_REQUESTED"]
  if blockers:
    print(f"Changes requested by: {', '.join(blockers)}; refusing.")
    return 1

  merge_status, result = api("PUT", f"/repos/{repo}/pulls/{pr_number}/merge", token, {
    "merge_method": "squash",
    "commit_title": f"{pr['title']} (#{pr_number})",
  })
  if merge_status == 200:
    print(f"Squash-merged PR #{pr_number}: {result.get('sha', '')}")
    return 0
  print(f"Merge rejected: {merge_status} {result}")
  return 1


if __name__ == "__main__":
  sys.exit(main())
