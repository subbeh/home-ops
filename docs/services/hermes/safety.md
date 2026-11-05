---
covers:
  - ansible/services/docker-socket-proxy.yaml
---
# Safety

Hermes reads the web and runs commands, so a web page can try to steer it (prompt injection). These are the guards, and what they don't stop. Upstream: [security](https://hermes-agent.nousresearch.com/docs/user-guide/security).

## Manual approvals

`approvals.mode` is `manual`. Before a dangerous command, Hermes posts an approval card in Discord (Allow Once, Allow Session, Always Allow, Deny) and waits. No answer within 5 minutes counts as Deny.

- Only users in `DISCORD_ALLOWED_USERS` can press the buttons; text a plugin injects can't approve.
- Hermes's default mode, `smart`, lets a model approve dangerous commands itself. That's why it's set to `manual` by hand (setup step 4 in [`hermes.yaml`](../../../ansible/services/hermes.yaml)'s header).
- Runs with nobody to ask, such as cron jobs, get Deny.
- "Allow Session" and "Always Allow" skip the question for that kind of command from then on. Review `command_allowlist` in `config.yaml` now and then.
- `approvals.mode: off` and a session's `/yolo` skip approvals. Don't use them.

## The Docker socket proxy

Hermes may list containers and read their logs, so it can tell what's wrong with a Service (the `ops` Profile's [homelab plugin](profiles.md#the-homelab-plugin) does). It gets that through the [`docker-socket-proxy`](../../../ansible/services/docker-socket-proxy.yaml) Service ([wollomatic/socket-proxy](https://github.com/wollomatic/socket-proxy)), never the Docker socket itself:

- The proxy allows only `GET` on `/containers/json` (the list) and `/containers/<id>/logs`. Everything else gets 403 or 405.
- Inspect stays blocked on purpose: a container's inspect output holds its env, and on the vps that includes the BWS access token, the Semaphore admin password, the restic credentials and the Cloudflare token.
- The proxy has no network at all. It serves a unix socket in its data dir, which only hermes mounts, read-only, at `/run/docker-proxy`. It runs read-only with every capability dropped.
- Confusing part: the docker CLI can't use it. `docker logs` inspects the container first, which the proxy refuses. Talk to the raw API over the socket instead, for example `curl --unix-socket /run/docker-proxy/proxy.sock http://d/containers/json`.

## Resource limits

The vps has no swap, so a runaway agent could get other Services killed for memory. The container has its own memory and CPU caps in `hermes.yaml`: 2 GiB and 1.5 CPUs.

- **At rest**: about 0.8 GB after a restart, growing to about 1.05 GB over a day. The gateway and the dashboard take about 450 MB each.
- **Kanban workers**: each running card is a worker of about 290 MB. `kanban.max_in_progress: 2` in the default Profile's `config.yaml` lets at most two run at once; the rest wait as `ready`. Two workers on top of a day-old baseline come to about 1.65 GB, leaving the rest for tool runs.
- Confusing part: unset isn't unlimited. Hermes then derives a cap from `/proc/meminfo`, which shows the vps's whole memory and not the container's limit, so it allowed 7 workers.
- The gateway reads the cap at startup: after changing it, `docker restart hermes` (check `hermes kanban list` first, since a restart kills running workers).

## What one Profile can see of another

All Profiles share one container and its filesystem. Any Profile with a terminal can read every other Profile's files, `.env` keys and memory. This was a deliberate choice for the vps's memory ([README.md](README.md)): the guards above stop mistakes and casual prompt injection, not a determined attacker who has taken over a Profile.

Langfuse traces carry metadata only, so chat content stays off Langfuse Cloud ([profiles.md](profiles.md)).

## The Deploy tool

The `ops` Profile's `homelab_deploy` ([profiles.md](profiles.md#the-homelab-plugin)) starts a Deploy of one Service through Semaphore, gated like a dangerous command. Upstream: [pre_tool_call](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks#pre_tool_call).

- A `pre_tool_call` hook in the plugin checks the Service against `deployable.json`, which each hermes Deploy writes into the plugin dir from the vps's Services in `inventory.yml`, minus semaphore (recreating it kills the running task) and hermes (ops' own container). Anything else is refused before any prompt; a missing file refuses everything.
- For a deployable Service, the hook asks for approval, which posts the usual approval card. Deny, a timeout, an error in the gate, or a run with nobody to ask (cron) starts nothing.
- Each call gets its own `rule_key`, so "Allow Session" or "Always Allow" never covers a later Deploy. The cost: "Always Allow" leaves a dead entry in `command_allowlist`.
- The tool uses the `hermes-ops` Semaphore user's token from ops' `.env` ([keys.md](keys.md)), which the plugin reads per call, outside the terminal. Because Profiles share a filesystem, any Profile's terminal could still read it: the gate stops mistakes, not a determined attacker.
- `approvals.mode: off` or `/yolo` would skip this gate too.
