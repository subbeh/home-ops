"""The morning-brief cron job's pre-check script (docs/services/hermes/profiles.md#cron-jobs).

Prints the OpenCode Go plan's usage meters and this billing month's spend per model, for the brief
to copy. It reads the console API the Billing drawer uses, with Hermes's own Go key. It always
exits 0 and says when OpenCode can't be read, so the brief still posts.
"""

import json
import urllib.request
from datetime import datetime
from pathlib import Path

# Go Plus monthly allowance per model, in dollars (https://opencode.ai/docs/go/). What blocks is
# the plan's shared meters (go/status); the per-model lines only show which model is spending.
ALLOWANCE = {
    "glm-5.3-flash": 180,
    "deepseek-v4.1-flash": 200,
    "deepseek-v4-pro": 60,
    "kimi-k3.1-pro": 60,
    "mimo-v2.6-pro": 60,
}
FLAG = 0.75
API = "https://opencode.ai/console/api/"
DATA = Path(__file__).resolve().parent.parent


def get(path, key):
    # Undocumented console API; Cloudflare blocks urllib's default User-Agent.
    req = urllib.request.Request(API + path, headers={"Authorization": f"Bearer {key}", "User-Agent": "hermes-go-usage"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def dollars(micro_cents):
    return int(micro_cents) / 1e8


def meter_line(name, m):
    used, limit = dollars(m["usedMicroCents"]), dollars(m["limitMicroCents"])
    resets = datetime.fromisoformat(m["resetsAt"].replace("Z", "+00:00")).astimezone()  # the container's TZ is local
    flag = " ⚠ over 75%" if used > FLAG * limit else ""
    return f"- {name}: ${used:.2f} of ${limit:.0f} ({used / limit:.0%}), resets {resets:%a %d %b %H:%M}{flag}"


def report(status, models):
    meters = status["access"]["meters"]
    lines = [f"OpenCode Go usage ({status['product']}), shared by all models:"]
    if dollars(meters["fiveHour"]["usedMicroCents"]) > FLAG * dollars(meters["fiveHour"]["limitMicroCents"]):
        lines.append(meter_line("5 hours", meters["fiveHour"]))
    lines += [meter_line("Week", meters["week"]), meter_line("Month", meters["month"]), "This billing month per model:"]
    for item in models:
        cost, cap = dollars(item["totalCostMicroCents"]), ALLOWANCE.get(item["model"])
        if cap is None:
            lines.append(f"- {item['model']}: ${cost:.2f} (allowance not in go-usage.py)")
        else:
            flag = " ⚠ over 75%" if cost > FLAG * cap else ""
            lines.append(f"- {item['model']}: ${cost:.2f} of ${cap} ({cost / cap:.0%}){flag}")
    if not models:
        lines.append("- No usage yet.")
    return "\n".join(lines)


def main():
    try:
        env = dict(l.strip().split("=", 1) for l in (DATA / ".env").read_text().splitlines() if "=" in l and l[0] != "#")
        key = env["OPENCODE_GO_API_KEY"].strip('"')
        status = get("go/status", key)
        # shortcut: from= takes a date, so the billing month's first day counts whole; fine for a brief.
        since, today = status["access"]["startsAt"][:10], datetime.now().date().isoformat()
        models = get(f"usage/models?range=30d&from={since}&to={today}&page=1&pageSize=50&costOrder=desc", key)["items"]
        print(report(status, models))
    except Exception as e:  # any failure, a bad key included: the brief posts without usage
        print(f"OpenCode Go usage unavailable: the console API couldn't be read ({type(e).__name__}).")


if __name__ == "__main__":
    main()
