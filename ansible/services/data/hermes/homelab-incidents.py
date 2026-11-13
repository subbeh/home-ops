"""Pre-check for the ops Profile's homelab-incidents cron job (docs/services/hermes/profiles.md).

Prints each Gatus endpoint that went down since the last check, with its latest failure, so ops
diagnoses it from the container's logs and recent Deploys. An endpoint counts once per incident:
it stays in the down list until a check finds it up again. The last line is the wake gate:
{"wakeAgent": false} when nothing new is down, so a quiet tick makes no model call.
"""

import json
import urllib.request
from pathlib import Path

# On the services network, which hermes joins; results come oldest first.
GATUS_URL = "http://gatus:8080/api/v1/endpoints/statuses"
# Gatus's default alert failure-threshold, so a wake matches a Pushover alert and a Deploy's
# container recreate doesn't count.
THRESHOLD = 3
# Endpoint keys down at the last check, next to this script in the Profile's scripts dir.
DOWN = Path(__file__).with_suffix(".down.json")


def down(endpoints):
    """Endpoints whose last THRESHOLD results all failed, by key, with the latest failure."""
    out = {}
    for ep in endpoints:
        last = (ep.get("results") or [])[-THRESHOLD:]
        if len(last) == THRESHOLD and not any(r.get("success") for r in last):
            out[ep["key"]] = {
                "name": ep.get("name"),
                "group": ep.get("group"),
                "failing_since": last[0].get("timestamp"),
                "errors": last[-1].get("errors") or [],
                "failed_conditions": [c.get("condition") for c in last[-1].get("conditionResults") or [] if not c.get("success")],
            }
    return out


def main():
    try:
        with urllib.request.urlopen(GATUS_URL, timeout=30) as resp:
            now = down(json.load(resp))
    except (OSError, ValueError) as e:
        # A stopped Gatus can't alert about itself, so its outage is an incident too.
        now = {"gatus-api": {"name": "gatus", "errors": [f"Gatus API unreachable: {e}"]}}
    seen = set(json.loads(DOWN.read_text())) if DOWN.exists() else set()
    new = [k for k in now if k not in seen]
    for key in new:
        print(f"## {key}\n{json.dumps(now[key], indent=2)}\n")
    DOWN.write_text(json.dumps(sorted(now)))
    print(json.dumps({"wakeAgent": bool(new)}))


if __name__ == "__main__":
    main()
