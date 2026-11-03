"""Pre-check for the ops Profile's actions-failures cron job (docs/services/hermes/profiles.md).

Prints each GitHub Actions run of the repo that failed since the last check, with the log tail of
its failed jobs, so the agent diagnoses it in one model call. The last line is the wake gate:
{"wakeAgent": false} when nothing new failed, so a quiet tick makes no model call.
"""

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

REPO = "subbeh/home-ops"
FAILED = {"failure", "timed_out", "startup_failure"}
TAIL = 60
# Run keys already seen, next to this script in the Profile's scripts dir.
SEEN = Path(__file__).with_suffix(".seen.json")


def get(path):
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}{path}")
    # Unredirected: the logs endpoint redirects to blob storage, which must not get the token.
    req.add_unredirected_header("Authorization", f"Bearer {os.environ['GITHUB_ACTIONS_TOKEN']}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


def failed_runs():
    runs = json.loads(get("/actions/runs?status=completed&per_page=50"))["workflow_runs"]
    # Fork PRs are left out: their logs are a stranger's text, and ops will hold Deploy power.
    return {
        f"{r['id']}-{r['run_attempt']}": r
        for r in runs
        if r["conclusion"] in FAILED and (r.get("head_repository") or {}).get("full_name") == REPO
    }


def log_tail(log):
    """The TAIL lines up to the last error, without timestamps; GitHub appends cleanup steps."""
    lines = [re.sub(r"^\S+Z ", "", line) for line in log.splitlines()]
    errors = [i for i, line in enumerate(lines) if "##[error]" in line]
    end = errors[-1] + 1 if errors else len(lines)
    return "\n".join(lines[max(0, end - TAIL) : end])


def report(run):
    print(f"## {run['name']} #{run['run_number']}: {run['conclusion']} on {run['head_branch']} ({run['event']})")
    print(f"{run['html_url']}\n{run['display_title']}\n")
    jobs = json.loads(get(f"/actions/runs/{run['id']}/attempts/{run['run_attempt']}/jobs"))["jobs"]
    for job in (j for j in jobs if j["conclusion"] in FAILED):
        step = next((s["name"] for s in job.get("steps", []) if s["conclusion"] in FAILED), "?")
        print(f"### Job {job['name']}, failed step: {step}")
        try:
            print(log_tail(get(f"/actions/jobs/{job['id']}/logs")), "\n")
        except urllib.error.HTTPError as e:
            print(f"(log unavailable: HTTP {e.code})\n")


def main():
    try:
        runs = failed_runs()
    except OSError as e:
        if isinstance(e, urllib.error.HTTPError) and e.code < 500:
            raise  # a bad or expired token: fail the job, so Hermes delivers the error
        print('{"wakeAgent": false}')  # GitHub is down: the next tick catches up
        return
    seen = set(json.loads(SEEN.read_text())) if SEEN.exists() else None
    # The first run only records what already failed.
    new = [] if seen is None else [k for k in runs if k not in seen]
    for key in new:
        report(runs[key])
    SEEN.write_text(json.dumps(sorted(runs)))
    print(json.dumps({"wakeAgent": bool(new)}))


if __name__ == "__main__":
    main()
