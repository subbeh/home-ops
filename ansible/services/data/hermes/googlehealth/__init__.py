"""Read-only Google Health API tools (the user's Fitbit data) for the health Profile; see
docs/services/hermes/profiles.md.

The Deploy copies this dir into the health Profile's own plugins dir, so no other Profile can load it.
The OAuth client and refresh token are read here, per call, so they never reach the terminal or the
model's context. Upstream: https://developers.google.com/health
"""

import datetime
import json
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://health.googleapis.com/v4/users/me"
TOKEN_URL = "https://oauth2.googleapis.com/token"
# dailyRollUp types and their longest range in days (the API refuses longer).
DAILY_TYPES = {"steps": 90, "distance": 90, "active-zone-minutes": 90, "weight": 90,
               "active-minutes": 14, "heart-rate": 14, "total-calories": 14}
# reconcile types (one merged point per record) and the field their date filter is on.
RECORD_TYPES = {
    "sleep": "sleep.interval.civil_end_time",
    "exercise": "exercise.interval.civil_end_time",
    "daily-resting-heart-rate": "daily_resting_heart_rate.date",
    "daily-heart-rate-variability": "daily_heart_rate_variability.date",
    "daily-oxygen-saturation": "daily_oxygen_saturation.date",
    "daily-respiratory-rate": "daily_respiratory_rate.date",
}
RECORD_MAX_DAYS = 90
# Sleep and exercise pages hold 25 points; enough for 90 days of nightly sleep.
MAX_PAGES = 8
# Per-stage timelines run to hundreds of entries a night; the summary carries the stage minutes.
DROP_KEYS = {"stages"}

_token = {"value": None, "expires": 0.0}


def date_range(params, max_days):
    """start_date and end_date (inclusive, YYYY-MM-DD) to (start, end exclusive) dates. Parsing them
    is also what keeps model input out of the filter syntax."""
    start = datetime.date.fromisoformat(str(params.get("start_date")))
    end = datetime.date.fromisoformat(str(params.get("end_date") or params.get("start_date")))
    if end < start:
        raise ValueError("end_date is before start_date")
    days = (end - start).days + 1
    if days > max_days:
        raise ValueError(f"{days} days asked; this data type takes at most {max_days} per call")
    return start, end + datetime.timedelta(days=1)


def record_filter(field, start, end):
    return f'{field} >= "{start.isoformat()}" AND {field} < "{end.isoformat()}"'


def civil(day):
    return {"date": {"year": day.year, "month": day.month, "day": day.day},
            "time": {"hours": 0, "minutes": 0, "seconds": 0, "nanos": 0}}


def summarize_rollup(points):
    """dailyRollUp points to {date, <value fields>}; a day with no value means not worn, not zero."""
    out = []
    for p in points:
        d = (p.get("civilStartTime") or {}).get("date") or {}
        item = {"date": f"{d.get('year', 0):04d}-{d.get('month', 0):02d}-{d.get('day', 0):02d}"}
        for key, value in p.items():
            if key not in ("civilStartTime", "civilEndTime"):
                item.update(value if isinstance(value, dict) else {key: value})
        out.append(item)
    return out


def trim(value):
    """Drop the bulky per-stage timelines, recursively."""
    if isinstance(value, dict):
        return {k: trim(v) for k, v in value.items() if k not in DROP_KEYS}
    if isinstance(value, list):
        return [trim(v) for v in value]
    return value


def _secret(name):
    # From the health Profile's .env (the googlehealth Key set): non-default Profiles never see the
    # container env under the multiplexed gateway.
    from agent.secret_scope import get_secret

    value = get_secret(name)
    if not value:
        raise RuntimeError(f"{name} is not set in this Profile's .env")
    return value


def _request(url, data=None, headers=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data, headers or {}), timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:  # Google's body says why, e.g. ACCOUNT_NOT_LINKED
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:300].decode(errors='replace')}") from None


def _access_token():
    if _token["value"] and time.time() < _token["expires"]:
        return _token["value"]
    form = urllib.parse.urlencode({
        "client_id": _secret("GOOGLE_HEALTH_CLIENT_ID"),
        "client_secret": _secret("GOOGLE_HEALTH_CLIENT_SECRET"),
        "refresh_token": _secret("GOOGLE_HEALTH_REFRESH_TOKEN"),
        "grant_type": "refresh_token",
    }).encode()
    body = _request(TOKEN_URL, form, {"Content-Type": "application/x-www-form-urlencoded"})
    _token["value"] = body["access_token"]
    _token["expires"] = time.time() + int(body.get("expires_in", 3600)) - 60
    return _token["value"]


def _api(path, query=None, body=None):
    url = f"{API}/{path}" + (f"?{urllib.parse.urlencode(query)}" if query else "")
    headers = {"Authorization": f"Bearer {_access_token()}", "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    return _request(url, data, headers)


def _tool(fn):
    def handler(params, **kwargs):
        try:
            return json.dumps(fn(params or {}))
        except Exception as e:  # the model gets the reason instead of a failed turn
            return json.dumps({"error": f"{type(e).__name__}: {e}"})
    return handler


def _type(params, allowed):
    data_type = params.get("data_type")
    if data_type not in allowed:
        raise ValueError(f"{data_type!r} is not one of {sorted(allowed)}")
    return data_type


@_tool
def daily(params):
    data_type = _type(params, DAILY_TYPES)
    start, end = date_range(params, DAILY_TYPES[data_type])
    body = {"range": {"start": civil(start), "end": civil(end)}, "windowSizeDays": 1}
    resp = _api(f"dataTypes/{data_type}/dataPoints:dailyRollUp", body=body)
    return {"data_type": data_type, "days": summarize_rollup(resp.get("rollupDataPoints") or []),
            "source": "Google Health API (Fitbit)"}


@_tool
def records(params):
    data_type = _type(params, RECORD_TYPES)
    start, end = date_range(params, RECORD_MAX_DAYS)
    query = {"filter": record_filter(RECORD_TYPES[data_type], start, end)}
    points = []
    for _ in range(MAX_PAGES):
        resp = _api(f"dataTypes/{data_type}/dataPoints:reconcile", query)
        points += resp.get("dataPoints") or []
        if not resp.get("nextPageToken"):
            break
        query["pageToken"] = resp["nextPageToken"]
    return {"data_type": data_type, "records": trim(points), "source": "Google Health API (Fitbit)"}


_DATES = {
    "start_date": {"type": "string", "description": "First day, YYYY-MM-DD, local time"},
    "end_date": {"type": "string", "description": "Last day, inclusive, YYYY-MM-DD; defaults to start_date"},
}


def _schema(name, description, types):
    props = {"data_type": {"type": "string", "enum": sorted(types)}, **_DATES}
    return {"name": name, "description": description,
            "parameters": {"type": "object", "properties": props, "required": ["data_type", "start_date"]}}


TOOLS = [
    (daily, _schema("googlehealth_daily",
        "The user's Fitbit totals per day from the Google Health API: steps, distance (mm), active and "
        "active-zone minutes, heart rate, total calories (kcal) or weight. At most 14 days for "
        "active-minutes, heart-rate and total-calories, 90 for the rest. A day missing from the result "
        "means the tracker wasn't worn, not zero.", DAILY_TYPES)),
    (records, _schema("googlehealth_records",
        "The user's Fitbit records from the Google Health API, merged across sources: sleep sessions "
        "(with minutes asleep, awake and per stage), exercise sessions, and daily resting heart rate, "
        "heart rate variability, oxygen saturation and respiratory rate. Sleep and exercise match on "
        "the day they ended. At most 90 days per call.", RECORD_TYPES)),
]


def register(ctx):
    for handler, schema in TOOLS:
        ctx.register_tool(name=schema["name"], toolset="googlehealth", schema=schema, handler=handler)
