---
covers:
  - ansible/services/hermes.yaml
  - ansible/services/tasks/hermes-*.yaml
---
# Running Hermes

Hermes commands run inside the container on the vps: `docker exec -it hermes hermes <command>`, adding `-p <profile>` for a Profile other than default.

## Deploying hermes

A hermes Deploy recreates the container, so it restarts every Profile at once and kills running Kanban workers ([kanban.md](kanban.md)).

1. **Deploy from `main` only**, after the change has landed there. A Deploy from a branch or worktree puts that branch's `hermes.yaml` live and undoes anything else already on `main`; this has reverted another change before.
2. **Check for running cards**: `docker exec hermes hermes kanban list`. If any are running, wait, or accept that they rerun from the start.
3. **Preview, then Deploy** ([deploy.md](../../runbooks/deploy.md)):

   ```sh
   just ansible::playbook services --tags hermes --check --diff
   just ansible::playbook services --tags hermes
   ```

The Deploy also runs the two post-tasks: it writes each Profile's keys ([keys.md](keys.md)) and keeps Kanban notices plain. Its output is hidden (`no_log`), since it renders secrets.

Settings that Hermes owns (`config.yaml`, Profiles, plugins, `SOUL.md`) don't change with a Deploy: they're made by hand inside the container and survive recreates in the data dir. Record each lasting one as a line in `hermes.yaml`'s header and update these docs, since no hook catches changes made only on the vps.

## Everyday tasks

- **Add a Profile**: [profiles.md](profiles.md#adding-a-profile).
- **Rotate or add a key**: [keys.md](keys.md#rotating-a-key).
- **Change a Profile's model**: `docker exec -it hermes hermes -p <profile> model`, then update the table in [profiles.md](profiles.md) and the header line.

## Health and logs

- **Gatus** checks two endpoints: `hermes` (the dashboard's login page answers) and `hermes-gateway` (the dashboard's `/api/status` reports the gateway running and Discord connected). The gateway's own port listens on loopback only, so Gatus asks the dashboard.
- **Logs**: `docker logs hermes` on the vps, or the dashboard.
- **Model calls**: traces in Langfuse Cloud ([profiles.md](profiles.md#models-and-costs)).
- **Quick model check** for one Profile: `docker exec hermes hermes -p <profile> chat --oneshot -Q -q "Reply with ok."`.

## Common failures

| Symptom | Cause and fix |
|---|---|
| A non-default Profile fails every model call | Its key is missing. Is it listed under `hermes_profiles` with the `model` Key set, and was hermes Deployed since? Check its `.env` has the managed block. |
| A rotated key isn't used | The key changed in BWS but hermes wasn't Deployed since. Deploy. |
| Cards wait about 15 minutes after a Deploy | The hostname isn't fixed. `docker inspect hermes --format '{{.Config.Hostname}}'` must print `hermes`; a Deploy from an old branch can undo it. Deploy from `main`. |
| The default Profile replies to a card notice by reading `kanban.db` | A subscription is on `notify+wake`. Deploy hermes, which switches it back and re-adds the triggers. |
| The dashboard acts as if served over plain http behind traefik | `public_url` or `trusted_proxies` under `dashboard:` in `config.yaml` is wrong, so traefik's `X-Forwarded-Proto` is ignored (setup step 2 in the header). |
| `hermes-gateway` is down in Gatus | The gateway crashed or Discord dropped. Check `docker logs hermes`; a restart (`docker restart hermes`) reconnects. |
| The container restarts under load | It hit its memory cap. Check `docker stats hermes`, and how many Kanban workers were running. |
