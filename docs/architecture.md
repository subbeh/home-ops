---
covers:
  - ansible/group_vars/all/services.yaml
  - ansible/roles/services/tasks/main.yaml
  - ansible/roles/services/tasks/gatus.yaml
  - ansible/services/traefik.yaml
  - ansible/services/restic.yaml
  - ansible/services/backrest.yaml
  - ansible/services/gatus.yaml
  - terraform/cloudflare/main.tf
  - terraform/cloudflare/records.auto.tfvars
  - terraform/tailscale/main.tf
  - terraform/tailscale/policy.hujson
---
# Architecture

## Hosts

Services run on `vps` and on `nas-svc` at home; see [hosts.md](hosts.md). The inventory groups Hosts by location (`remote`, `local`), OS (`debian`) and function (`pve`, `vm`, `k8s`). The function groups are empty placeholders. Services are assigned to individual Hosts only, through `services:` in host vars.

## Network, DNS and TLS

Everything is reachable only over the tailnet, and home Services also from the clients Network.

- **Traefik** publishes `:80` and `:443` on the VPS's tailnet address only, and redirects HTTP to HTTPS. Containers opt in with the `traefik.enable` label. A Service's hostname defaults to `<container name>.<services_domain>`; a `traefik.http.routers.<name>.rule` label overrides it (opengym → `gym.`). Traefik's own dashboard is served at `traefik.<services_domain>`. Backends that serve only HTTPS with a self-signed cert (unifi) set `loadbalancer.server.scheme: https` and reference Traefik's `skip-verify@file` serversTransport, defined in its file-provider config.
- **DNS**: every record lives in the `records` map in `terraform/cloudflare/records.auto.tfvars`, except the DNS-only wildcard `*.vps.sbbh.cloud` → the VPS's tailnet IP, which `terraform/cloudflare/main.tf` adds. The names resolve publicly, but the IP only connects from the tailnet.
- **Home names**: `home.sbbh.cloud` (Hosts) and `svc.sbbh.cloud` (the home ingress) have no public records. Tailscale split DNS (`terraform/tailscale/main.tf`) sends both to OPNsense's Unbound on its servers address (`10.11.20.1`), reached over its subnet route, so they resolve on any tailnet device that accepts routes, at home or away.
- **TLS**: a wildcard Let's Encrypt cert through a Cloudflare DNS-01 challenge, so nothing has to be reachable from the internet.
- **Home ingress**: Services on `local` Hosts are served at `https://<service>.<ingress_domain>` (`svc.sbbh.cloud`) by HAProxy on OPNsense, not by Traefik. A Service opts in with `ingress: {port: N}`, the port it publishes on its Host. `ansible/playbooks/opnsense.yaml` generates the routes (the `ingress_routes` filter), the `*.svc.sbbh.cloud` Unbound override and a wildcard cert through the same Cloudflare DNS-01 challenge; see [runbooks/opnsense.md](runbooks/opnsense.md#home-ingress). There's no public record.
- **Private Services**: a Service whose file must stay out of the public repo is `ansible/services/<name>.private.yaml`, gitignored, so it exists only in the main checkout. Its name and Assignment stay in `inventory.yml`, and its name in `services_private`, so the services role skips it where the file is missing (Semaphore, CI, worktrees). `just docs` ignores private files and Gatus gets no check for them; deploy them from the main checkout only.
- `network_mode: host` containers (syncthing) are reached at `host.docker.internal`. aven also publishes its port on the tailnet address for sync clients.
- **Tailnet policy** (`terraform/tailscale/policy.hujson`, owned in full by Terraform): members reach everything; `tag:ci` (the ephemeral Auto-deploy node) reaches only `vps:443`. `autoApprovers` approve the subnet routes in `tailnet_routes` and the exit node, for admins. The policy `tests` enforce the `tag:ci` limit and that the VPS can ping each routed Network, on every plan.

The VPS's tailnet IP is written once, in `ansible/group_vars/all/network.yaml` (`networks.tailnet.addresses.vps`). The `cloudflare` stack reads it for the wildcard and the `tailscale` stack templates it, and `tailnet_routes`, into `policy.hujson`, and both workspaces run on a change to that file.

## Secrets

Bitwarden Secrets Manager is the only place secrets live.

- **Adding one**: put it in `.bws.yaml` (gitignored). The dotfiles bws sync creates it in Secrets Manager, so there's no `bws secret create` to run.
- **Ansible**: the services role runs `bws secret list` on the controller once per run (retried, since the Bitwarden API fails now and then) and exposes every secret the `BWS_ACCESS_TOKEN` can read as `bws_secrets.<KEY>`. Services that reference secrets set `no_log: true`, which also hides their diffs.
- **Terraform**: `terraform/tfe-admin` copies the secrets each workspace needs into sensitive TFC env vars, and the deploy workflow's into GitHub Actions secrets.
- **Tokens**: the laptop's `BWS_ACCESS_TOKEN` comes from `.env`, which mise loads. Semaphore uses its own machine account.

## Data

Each Service keeps its state in `/opt/data/<service>` (`services_data_dir`), owned by the `apps` user (2000:2000). The role creates that directory for any Service with files or containers. The laptop's workspace, synced by syncthing, sits outside it in `/opt/workspace` (`services_workspace_dir`), also owned by `apps`, so any Service can mount it. Syncthing mounts it at its old path inside its data dir. Every container joins the `services` bridge network and gets the shared defaults from `services_container_defaults`. Each Deploy pulls images and recreates containers, then removes every image no container uses, so replaced versions don't fill the disk.

## Backups

restic backs up all of `/opt/data` and `/opt/workspace` every hour, on the hour, to a dedicated Hetzner Storage Box sub-account over SFTP (`ansible/services/restic.yaml`). It excludes restic's own SSH key.

- **SQLite**: at :55 a root cron on the Host writes a consistent copy of every SQLite db under `/opt/data` to `/opt/data/restic/sqlite`, since a plain file copy can tear a db in WAL mode. Its own Gatus heartbeat alerts when a copy fails; restoring one: [runbooks/restore-backup.md](runbooks/restore-backup.md#restore-a-sqlite-db).
- **Retention**: forget runs after every backup, treats all snapshots as one group (the container's hostname changes on every recreate), and keeps 12 hourly, 7 daily, 4 weekly and 6 monthly snapshots.
- **Prune**: daily at 04:30, in its own container.
- **Check**: monthly, reading 5% of the data, in its own container.

Prune and check need an exclusive lock, so they start at :30, clear of the backup. Restoring: [runbooks/restore-backup.md](runbooks/restore-backup.md).

Backrest (`ansible/services/backrest.yaml`) is a web UI over the same repository, for browsing snapshots and downloading files. It only views: its prune, check and auto-unlock are off, so resticker alone backs up and cleans up the repository.

## Monitoring

Gatus (`ansible/services/gatus.yaml`) pings Tailscale DNS and the two home routers, pings every address on a routed home Network over the tailnet routes (from `network.yaml`, skipping any marked `monitor: false`), and checks every Service's URL through Traefik, so DNS, TLS and routing are covered too. It is also the dead-man's switch for backups: restic reports to a Gatus external endpoint after every run, and Gatus alerts if no report arrives within the heartbeat interval. Alerts go to Pushover.

A Service declares its own checks under a `gatus:` key (Gatus `endpoints` and `external-endpoints`), as restic does for its heartbeat. Its Deploy writes them to `/opt/data/gatus/config/services/<service>.yaml`, and Gatus merges every file in `/opt/data/gatus/config` and reloads on change. Endpoints without their own `alerts` alert to Pushover. Dropping the key removes the file on the Service's next Deploy. This only works for Services on Gatus's Host, the vps. Home Services behind the ingress get a generated check instead: `ingress.yaml` holds one HTTPS endpoint per committed route, resolved through OPNsense's Unbound on its tailnet address, so a new route needs a Deploy of gatus.
