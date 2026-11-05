---
name: manage-hermes
description: Change Hermes live on the vps (config.yaml, Profiles, cron jobs, Hermes skills, plugins), restart it, or Deploy it safely. Use when asked to configure, add a Profile to, schedule, extend, restart or roll back Hermes.
covers:
  - ansible/services/hermes.yaml
  - ansible/services/tasks/hermes-*.yaml
---
# Manage Hermes

[docs/services/hermes/](../../../docs/services/hermes/README.md) explains the setup, and [running.md](../../../docs/services/hermes/running.md) is the runbook. Read the page for the area you're changing first. Hermes owns its `config.yaml`, Profiles, cron jobs, skills and plugins: Ansible never writes them, so they change by hand on the vps and are recorded in the repo.

Run Hermes commands as `ssh vps docker exec hermes hermes [-p <profile>] <command>`, with `ssh -t` and `docker exec -it` for interactive ones (`model`, `profile create`). Add `-u hermes` when the command writes under `HOME` (npm), so it lands in the data dir. Paths below are inside the container: `/opt/data` is `/opt/data/hermes/data` on the vps.

## Steps for every live change

1. **Ask**: name the exact commands and any restart, and get the user's go-ahead. A live change is a real run, like a Deploy. First, when `agent-manager` is on PATH, lease Hermes: `agent-manager reserve live/vps/hermes --note "<what and why>" --ttl 1h --json`. A non-empty `conflicts` list means another session is changing Hermes live: release yours (`agent-manager release-files live/vps/hermes`) and name the holder and its note in the question. Hold the lease through step 6; reserving again from the same session renews it, so a Deploy handed to the deploy skill doesn't conflict with it.
2. **Check cards**: `hermes kanban list`. A restart or Deploy kills running workers, and their cards rerun from the start. If any are running, wait, or ask.
3. **Back up**: `cp <file> /opt/data/backups/<file>.pre-<change>` before editing. The hourly config history only snapshots at :50, so an edit and its rollback within the hour aren't in it.
4. **Change**: prefer `hermes config set <key> <value>`, because `hermes config` is interactive only. Edit `config.yaml` directly only for structures `config set` can't express (lists such as `gateway.profile_routes`). Profiles keep theirs in `/opt/data/profiles/<name>/config.yaml`.
5. **Reload**: the gateway reads routes, Kanban dispatcher settings, plugins and `.env` only at startup, so run `docker restart hermes` (step 2 first). Skills need only `/reload-skills` in Discord.
6. **Test**: `hermes -p <profile> chat --oneshot -Q -q "<prompt>"` for a Profile, model, tool or plugin. Done when the answer shows the change working. Then `agent-manager release-files live/vps/hermes`.
7. **Record**: add or edit a line in the one-time setup list in [`hermes.yaml`](../../../ansible/services/hermes.yaml)'s header, and update the docs page it touches. No hook catches a change made only on the vps. Commit on main with the hooks on.

To undo, restore from the backup or the config history ([Rolling back config](../../../docs/services/hermes/running.md#rolling-back-config)), then restart.

## Profiles

Follow [Adding a Profile](../../../docs/services/hermes/profiles.md#adding-a-profile). Besides the steps listed there:

- `--clone` copies default's fallback (glm-5.3-flash) and `.env`. A Profile whose own model is GLM gets a fallback from another family ([Models and costs](../../../docs/services/hermes/profiles.md#models-and-costs)). After the Deploy, delete every key outside the managed block that the Profile shouldn't have.
- Keys come from BWS through `hermes_key_sets` and `hermes_profiles` in `hermes.yaml`, never from the dashboard ([keys.md](../../../docs/services/hermes/keys.md#why-not-the-dashboard)).
- Create the Profile before adding a `gateway.profile_routes` entry for it: a route to a missing Profile makes the gateway reject the message.

## Cron jobs

The `cron create` commands in the `hermes.yaml` header are working examples; the rules are in [Cron jobs](../../../docs/services/hermes/profiles.md#cron-jobs).

- **Deliver**: `--deliver discord` posts to the home channel, `--deliver discord:<chat id>` to another channel.
- **Threads**: with `cron.mirror_delivery` on, a home-channel run opens a thread, which can end up private. A job that should post a plain message gets `attach_to_session: false` (header step 13 has the command).
- **Routed Profiles** (ops): their cron output isn't delivered yet ([upstream #144455](https://github.com/NousResearch/hermes-agent/issues/144455)). Read it in `/opt/data/profiles/<name>/cron/output/<job id>/`.
- **Pre-check scripts** get a scrubbed env: pass a key through with `hermes -p <profile> config set terminal.env_passthrough '[<KEY>]'`. Ship the script from the repo through `hermes.yaml`, as `actions-failures.py` is.
- **Test** with `hermes [-p <profile>] cron run <id>` and check Discord. Test a delivery change with a throwaway job, and remove it afterwards.

## Hermes skills

Default's skills live in `/opt/data/skills/<category>/<name>/SKILL.md` (the focus skills are in `productivity/`), a Profile's in `/opt/data/profiles/<name>/skills/`. Hermes drafts them and the user approves the wording. After an edit, run `/reload-skills` in Discord, then test with a one-shot or the slash command.

## Plugins

- **Upstream plugins**: `hermes [-p <profile>] plugins install <name> --yes-deps --enable`, then restart. They live in the data dir, so they survive a Deploy.
- **Repo plugins** (homelab): the hermes Deploy copies them into the Profile's `plugins/`. Enable once with `hermes -p <profile> plugins enable <name>`, then restart. Check one before shipping with `hermes plugins doctor <path> --ci` and `just docs-test`.

## Restart or Deploy

A Deploy is needed only when the repo side changed (`hermes.yaml`, key sets, shipped files, post-tasks). Hand it to the deploy skill, plus:

- **From main only**: a Deploy from a worktree puts that branch's `hermes.yaml` live and has already reverted another worker's change. When several workers changed hermes, land them all on main and run one Deploy from the main checkout.
- **Check cards first** (step 2): a Deploy recreates the container.
- **No diff**: hermes is `no_log`, so the preview and the recap show no details. Check the result on the vps instead: `docker inspect hermes --format '{{.Config.Hostname}}'` prints `hermes`, and a one-shot answers.

## Gotchas

- **Keys in the dashboard**: Providers > API keys writes outside the managed block and goes stale. Delete such lines from the `.env`.
- **Approvals**: never set `approvals.mode: off` or use `/yolo`. It also skips the gate on ops' Deploy tool ([safety.md](../../../docs/services/hermes/safety.md)).
- **One container**: a new bot or team member is a new Profile, never a new container.
