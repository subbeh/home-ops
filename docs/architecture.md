---
covers:
  - ansible/group_vars/all/services.yaml
  - ansible/roles/services/tasks/main.yaml
  - ansible/services/traefik.yaml
  - ansible/services/restic.yaml
  - ansible/services/gatus.yaml
  - terraform/cloudflare/main.tf
  - terraform/tailscale/policy.hujson
---
# Architecture

## Hosts

There's one Host today, `vps`; see [hosts.md](hosts.md). The inventory groups Hosts by location (`remote`, `local`), OS (`debian`) and function (`pve`, `vm`, `k8s`). The function groups are empty placeholders. Services are assigned to individual Hosts only, through `services:` in host vars.

## Network, DNS and TLS

Everything is reachable only over the tailnet.

- **Traefik** publishes `:80` and `:443` on the VPS's tailnet address only, and redirects HTTP to HTTPS. Containers opt in with the `traefik.enable` label. A Service's hostname defaults to `<container name>.<services_domain>`; a `traefik.http.routers.<name>.rule` label overrides it (opengym → `gym.`).
- **DNS**: `terraform/cloudflare` holds a DNS-only wildcard `*.vps.sbbh.cloud` → the VPS's tailnet IP. The names resolve publicly, but the IP only connects from the tailnet.
- **TLS**: a wildcard Let's Encrypt cert through a Cloudflare DNS-01 challenge, so nothing has to be reachable from the internet.
- `network_mode: host` containers (syncthing) are reached at `host.docker.internal`. aven also publishes its port on the tailnet address for sync clients.
- **Tailnet policy** (`terraform/tailscale/policy.hujson`, owned in full by Terraform): members reach everything; `tag:ci` (the ephemeral Auto-deploy node) reaches only `vps:443`. The policy `tests` enforce this on every plan.

The VPS's tailnet IP is written in three places: the inventory, `terraform/cloudflare/main.tf` and `policy.hujson`.

## Secrets

Bitwarden Secrets Manager is the only place secrets live.

- **Adding one**: put it in `.bws.yaml` (gitignored). The dotfiles bws sync creates it in Secrets Manager, so there's no `bws secret create` to run.
- **Ansible**: the services role runs `bws secret list` once per run and exposes every secret the `BWS_ACCESS_TOKEN` can read as `bws_secrets.<KEY>`. Services that reference secrets set `no_log: true`, which also hides their diffs.
- **Terraform**: `terraform/tfe-admin` copies the secrets each workspace needs into sensitive TFC env vars, and the deploy workflow's into GitHub Actions secrets.
- **Tokens**: the laptop's `BWS_ACCESS_TOKEN` comes from `.env`, which mise loads. Semaphore uses its own machine account.

## Data

Each Service keeps its state in `/opt/data/<service>` (`services_data_dir`), owned by the `apps` user (2000:2000). The role creates that directory for any Service with files or containers. Every container joins the `services` bridge network and gets the shared defaults from `services_container_defaults`. Each Deploy pulls images and recreates containers.

## Backups

restic backs up all of `/opt/data` every hour, on the hour, to a dedicated Hetzner Storage Box sub-account over SFTP (`ansible/services/restic.yaml`). It excludes restic's own SSH key.

- **Retention**: forget runs after every backup and keeps 12 hourly, 7 daily, 4 weekly and 6 monthly snapshots.
- **Prune**: daily at 04:30, in its own container.
- **Check**: monthly, reading 5% of the data, in its own container.

Prune and check need an exclusive lock, so they start at :30, clear of the backup. Restoring: [runbooks/restore-backup.md](runbooks/restore-backup.md).

## Monitoring

Gatus (`ansible/services/gatus.yaml`) pings Tailscale DNS and the two home routers. It is also the dead-man's switch for backups: restic reports to a Gatus external endpoint after every run, and Gatus alerts if no report arrives within the heartbeat interval. Alerts go to Pushover.
