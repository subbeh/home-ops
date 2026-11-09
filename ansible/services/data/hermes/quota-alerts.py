"""The default Profile's quota-alerts cron job (docs/services/hermes/kanban.md#quota-alerts).

Posts a Discord notice, one per event, when a Kanban card keeps hitting the usage limit, a goal
enters a third or later review round, or spend passes SPEND_LIMIT in an hour. It runs with
--no-agent and posts through `hermes send`, so it makes no model call and still reports when the
limit has hit every model. Empty stdout keeps the job silent; a crash makes Hermes post the error.
"""

import base64
import json
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from itertools import takewhile
from pathlib import Path

STUCK_RUNS = 3
REVIEW_ROUNDS = 3
SPEND_LIMIT = 3.0  # dollars per hour, as Langfuse prices it; normal hours stay under $2
HOME_CHANNEL = "discord"
# Notices sent so far, next to this script; survives a Deploy like the rest of the data dir.
SEEN = Path(__file__).with_suffix(".seen.json")
DATA = Path(__file__).resolve().parent.parent


def post(target, text):
    r = subprocess.run(["hermes", "send", "-t", target, text], capture_output=True, text=True, timeout=60)
    if r.returncode:
        sys.exit(f"hermes send to {target} failed: {r.stderr or r.stdout}")


def profile_model(profile):
    home = DATA if profile == "default" else DATA / "profiles" / profile
    # A regex, so a stuck-card notice can't fail on what the job's Python has installed.
    m = re.search(r'^model:\s*(?:#.*\s*)*(?:default:\s*)?"?([\w./-]+)', (home / "config.yaml").read_text(), re.M)
    return m.group(1) if m else "unknown model"


def reset_time(card):
    log = DATA / "kanban" / "logs" / f"{card}.log"
    found = re.findall(r"Limit resets at [^\n]*", log.read_text(errors="replace")) if log.exists() else []
    return found[-1] if found else "Reset time unknown."


def target_for(db, card):
    row = db.execute(
        "SELECT thread_id FROM kanban_notify_subs WHERE task_id = ? AND platform = 'discord' AND thread_id != ''",
        (card,),
    ).fetchone()
    return f"discord:{row[0]}" if row else HOME_CHANNEL


def stuck_cards(db):
    """Open cards whose last STUCK_RUNS finished runs were all rate-limited: Hermes requeues those
    without counting a failure, so they never block. A run in progress doesn't end the spell."""
    open_cards = db.execute(
        "SELECT id, title, assignee, model_override FROM tasks WHERE status IN ('ready', 'running')"
    ).fetchall()
    for card, title, profile, model in open_cards:
        runs = db.execute(
            "SELECT status, started_at FROM task_runs WHERE task_id = ? AND ended_at IS NOT NULL ORDER BY id DESC",
            (card,),
        ).fetchall()
        streak = list(takewhile(lambda r: r[0] == "rate_limited", runs))
        if len(streak) >= STUCK_RUNS:
            yield {"id": card, "title": title, "profile": profile, "model": model, "runs": len(streak), "since": streak[-1][1]}


def stuck_notice(c):
    secs = int(time.time()) - c["since"]
    # Card titles are model-written, sometimes from web pages: no @everyone from them.
    title = c["title"].replace("@", "@​")
    model = c["model"] or profile_model(c["profile"])
    return (
        f'⚠ Card {c["id"]} "{title}" has hit the usage limit on its last {c["runs"]} runs and is stuck, '
        f"holding a Kanban slot ({c['profile']}, {model}, {secs // 3600}h {secs % 3600 // 60}m so far). "
        f"{reset_time(c['id'])}\n"
        f"Wait for the reset, or switch model: `hermes kanban set-model {c['id']} <model> --provider opencode-go`."
    )


def check_stuck(db, seen):
    stuck = list(stuck_cards(db))
    ids = {c["id"] for c in stuck}
    seen["cards"] = [c for c in seen["cards"] if c in ids]  # one that ran normally starts a new spell
    for card in stuck:
        if card["id"] not in seen["cards"]:
            post(target_for(db, card["id"]), stuck_notice(card))
            seen["cards"].append(card["id"])


def review_rounds(db):
    """Reviewer cards per goal, for goals still open. Every card of a goal shares its thread."""
    # shortcut: goals started in a channel, not a thread, aren't counted; upgrade if those come back.
    return db.execute(
        """SELECT s.thread_id, COUNT(DISTINCT t.id) FROM tasks t
           JOIN kanban_notify_subs s ON s.task_id = t.id
           WHERE t.assignee = 'reviewer' AND t.status != 'archived' AND s.platform = 'discord' AND s.thread_id != ''
           GROUP BY s.thread_id HAVING COUNT(DISTINCT t.id) >= ? AND SUM(t.status != 'done') > 0""",
        (REVIEW_ROUNDS,),
    ).fetchall()


def check_rounds(db, seen):
    for thread, rounds in review_rounds(db):
        if rounds > seen["rounds"].get(thread, 0):
            post(
                f"discord:{thread}",
                f"⚠ This goal is on review round {rounds}. Each round reruns the costliest model over everything "
                "written so far. To stop it: `hermes kanban block <card> <why>`.",
            )
            seen["rounds"][thread] = rounds


def hourly_spend():
    """Dollars per model over the last hour, or None when Langfuse is unreachable."""
    keys = dict(l.strip().split("=", 1) for l in (DATA / ".env").read_text().splitlines() if "=" in l and l[0] != "#")
    token = f"{keys['HERMES_LANGFUSE_PUBLIC_KEY'].strip(chr(34))}:{keys['HERMES_LANGFUSE_SECRET_KEY'].strip(chr(34))}"
    now = datetime.now(timezone.utc)
    query = urllib.parse.urlencode(
        {
            "type": "GENERATION",
            "fromStartTime": (now - timedelta(hours=1)).isoformat(),
            "toStartTime": now.isoformat(),
            "fields": "core,basic,usage,model,metadata",
            "limit": 1000,  # far above an hour's generations; at most two workers run at once
        }
    )
    req = urllib.request.Request(
        f"https://cloud.langfuse.com/api/public/v2/observations?{query}",
        headers={"Authorization": "Basic " + base64.b64encode(token.encode()).decode()},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            observations = json.load(resp)["data"]
    except OSError as e:
        if isinstance(e, urllib.error.HTTPError) and e.code < 500:
            raise  # a bad or expired key: fail the job, so Hermes posts the error
        return None
    return go_spend(observations)


def go_spend(observations):
    """Dollars per model on OpenCode Go; the Langfuse project also holds other tools' traces."""
    spend = Counter()
    for o in observations:
        if (o.get("metadata") or {}).get("provider") == "opencode-go":
            spend[o.get("model") or "unknown"] += o.get("totalCost") or 0
    return spend


def check_spend(seen):
    spend = hourly_spend()
    if spend is None:
        return  # Langfuse is down: the next tick catches up
    total = sum(spend.values())
    if total <= SPEND_LIMIT:
        seen["spend"] = False  # re-arms for the next spike
    elif not seen["spend"]:
        top = ", ".join(f"{model} ${cost:.2f}" for model, cost in spend.most_common(3))
        post(HOME_CHANNEL, f"⚠ Hermes spent ${total:.2f} in the last hour (limit ${SPEND_LIMIT:.0f}): {top}.")
        seen["spend"] = True


def main():
    seen = json.loads(SEEN.read_text()) if SEEN.exists() else {"cards": [], "rounds": {}, "spend": False}
    db = sqlite3.connect(f"file:{DATA}/kanban.db?mode=ro", uri=True)
    try:
        check_stuck(db, seen)
        check_rounds(db, seen)
        check_spend(seen)
    finally:
        # Also on a failed post, so what was already sent isn't sent again.
        SEEN.write_text(json.dumps(seen))


if __name__ == "__main__":
    main()
