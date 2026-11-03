"""Read-only homelab tools for the ops Profile; see docs/services/hermes/profiles.md.

The Deploy copies this dir into the ops Profile's own plugins dir, so no other Profile can load it.
Tokens are read here, per call, so they never reach the terminal or the model's context.
"""

import http.client
import json
import re
import socket
import urllib.request

# Both on the services network, which hermes joins; no traefik or tailnet in between.
GATUS_URL = "http://gatus:8080/api/v1/endpoints/statuses"
# Project 1, as in .github/workflows/deploy.yaml.
SEMAPHORE_API = "http://semaphore:3000/api/project/1"
# The docker-socket-proxy Service's filtered socket: GET list and logs only.
DOCKER_SOCKET = "/run/docker-proxy/proxy.sock"
# The proxy's allowlist pattern for a container name; also keeps a name from changing the path.
CONTAINER_NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def summarize_statuses(endpoints):
    """Gatus statuses (results oldest first) to one line per endpoint, down ones first."""
    out = []
    for ep in endpoints:
        results = ep.get("results") or []
        fails = [r for r in results if not r.get("success")]
        last = results[-1] if results else {}
        item = {
            "key": ep.get("key"),
            "up": bool(last.get("success")) if results else None,
            "checked": last.get("timestamp"),
            "recent": f"{len(results) - len(fails)}/{len(results)} ok",
        }
        if fails:
            f = fails[-1]
            item["last_failure"] = {
                "at": f.get("timestamp"),
                "errors": f.get("errors") or [],
                "failed_conditions": [c.get("condition") for c in f.get("conditionResults") or [] if not c.get("success")],
            }
        out.append(item)
    return sorted(out, key=lambda i: (i["up"] is not False, i["key"] or ""))


def summarize_tasks(tasks, limit):
    """Semaphore tasks, newest first; tags are the Services a Deploy ran for."""
    tasks = sorted(tasks, key=lambda t: t.get("id") or 0, reverse=True)[:limit]
    return [{
        "id": t.get("id"),
        "status": t.get("status"),
        "tags": (t.get("params") or {}).get("tags"),
        "message": t.get("message"),
        "commit": (t.get("commit_hash") or "")[:7] or None,
        "created": t.get("created"),
        "end": t.get("end"),
    } for t in tasks]


def tail_output(lines, tail):
    """Semaphore task output rows to their last `tail` lines, without colour codes."""
    text = [ANSI.sub("", row.get("output") or "") for row in lines]
    return "\n".join(text[-tail:])


def summarize_containers(items):
    return sorted(({
        "name": (c.get("Names") or ["?"])[0].lstrip("/"),
        "image": c.get("Image"),
        "state": c.get("State"),
        "status": c.get("Status"),
    } for c in items), key=lambda c: c["name"])


def demux_logs(data):
    """Docker logs body to text. Without a TTY, Docker frames each chunk with an 8-byte header
    (stream, 3 zero bytes, big-endian length); with one, the body is raw. Inspect, which says which,
    is refused by the proxy, so the header is sniffed."""
    if len(data) < 8 or data[0] not in (0, 1, 2) or data[1:4] != b"\0\0\0":
        return data.decode(errors="replace")
    chunks, i = [], 0
    while i + 8 <= len(data):
        size = int.from_bytes(data[i + 4:i + 8], "big")
        chunks.append(data[i + 8:i + 8 + size])
        i += 8 + size
    return b"".join(chunks).decode(errors="replace")


def _get_json(url, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=15) as r:
        return json.load(r)


def _semaphore(path):
    # Per call, from the ops Profile's .env (the semaphore Key set): non-default Profiles never
    # see the container env under the multiplexed gateway.
    from agent.secret_scope import get_secret

    token = get_secret("HERMES_OPS_SEMAPHORE_TOKEN")
    if not token:
        raise RuntimeError("HERMES_OPS_SEMAPHORE_TOKEN is not set in this Profile's .env")
    return _get_json(SEMAPHORE_API + path, {"Authorization": f"Bearer {token}"})


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost", timeout=15)
        self._path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self._path)


def _docker(path):
    conn = _UnixConnection(DOCKER_SOCKET)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read()
    finally:
        conn.close()
    if resp.status != 200:
        raise RuntimeError(f"Docker API {path}: HTTP {resp.status} {body[:200].decode(errors='replace')}")
    return body


def _int(params, key, default, low, high):
    return max(low, min(high, int(params.get(key) or default)))


def _tool(fn):
    def handler(params, **kwargs):
        try:
            return json.dumps(fn(params or {}))
        except Exception as e:  # the model gets the reason instead of a failed turn
            return json.dumps({"error": f"{type(e).__name__}: {e}"})
    return handler


@_tool
def status(params):
    return summarize_statuses(_get_json(GATUS_URL))


@_tool
def tasks(params):
    # /tasks/last is the newest 200, enough for any recent Deploy.
    return summarize_tasks(_semaphore("/tasks/last"), _int(params, "limit", 10, 1, 50))


@_tool
def task_output(params):
    task_id = int(params["task_id"])
    return {"task_id": task_id, "output": tail_output(_semaphore(f"/tasks/{task_id}/output"), _int(params, "tail", 200, 1, 2000))}


@_tool
def containers(params):
    return summarize_containers(json.loads(_docker("/containers/json?all=true")))


@_tool
def container_logs(params):
    name = params.get("name") or ""
    if not CONTAINER_NAME.fullmatch(name):
        raise ValueError(f"not a container name: {name!r}")
    tail = _int(params, "tail", 100, 1, 1000)
    return {"name": name, "logs": demux_logs(_docker(f"/containers/{name}/logs?stdout=1&stderr=1&timestamps=1&tail={tail}"))}


def _schema(name, description, properties=None, required=None):
    return {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties or {}, "required": required or []}}


TOOLS = [
    (status, _schema("homelab_status",
        "Gatus health checks for every homelab Service: up or down now, recent results, and the last "
        "failure's errors and failed conditions. Down endpoints come first.")),
    (tasks, _schema("homelab_tasks",
        "Recent Semaphore tasks, newest first. Each is one Deploy (Auto-deploy or by hand): status, the "
        "Services it ran for (tags), message and commit.",
        {"limit": {"type": "integer", "description": "How many tasks, default 10, max 50"}})),
    (task_output, _schema("homelab_task_output",
        "The Ansible output of one Semaphore task, its last lines. Use after homelab_tasks to see why a "
        "Deploy failed.",
        {"task_id": {"type": "integer", "description": "Task id from homelab_tasks"},
         "tail": {"type": "integer", "description": "Lines from the end, default 200, max 2000"}},
        ["task_id"])),
    (containers, _schema("homelab_containers",
        "Every Docker container on the vps, running or not: name, image, state and status.")),
    (container_logs, _schema("homelab_container_logs",
        "The last log lines of one container on the vps, stdout and stderr, with timestamps.",
        {"name": {"type": "string", "description": "Container name from homelab_containers"},
         "tail": {"type": "integer", "description": "Lines from the end, default 100, max 1000"}},
        ["name"])),
]


def register(ctx):
    for handler, schema in TOOLS:
        ctx.register_tool(name=schema["name"], toolset="homelab", schema=schema, handler=handler)
