---
covers:
  - terraform/cloudflare/main.tf
---
# Rebuild the VPS

Draft. Facts that aren't in this repo are marked TODO.

> TODO(you): VPS provider, plan and region; how it's ordered or reinstalled.

## 1. Base system

> TODO(you): OS image (the inventory says `debian`, ADR 0001 says Ubuntu), SSH key for `root`, firewall rules, unattended upgrades.

- Install Docker and the Docker Python SDK. The role only checks for them, through its preflight, and never installs them.
  > TODO(you): the exact install steps used.

## 2. Tailnet

- Install Tailscale and join the tailnet as `vps`.
  > TODO(you): auth key or interactive login, tags, key expiry.
- The tailnet IP `100.77.96.125` is written in three places. Either give the new node that same IP in the Tailscale admin console, or update all three:
  - `ansible/inventory.yml`: `networks.tailnet.addr`
  - `terraform/cloudflare/main.tf`: the wildcard record
  - `terraform/tailscale/policy.hujson`: `hosts.vps`
- Check access from the laptop: `just ansible::playbook test-connection --limit vps`.

## 3. Data

1. Write restic's SSH setup only (its key is excluded from backups):

   ```sh
   just ansible::playbook services --tags restic,files --limit vps
   ```

2. Restore `/opt/data` as in [restore-backup.md](restore-backup.md), restoring everything (`--include /data`), before any Service starts.

## 4. Services

```sh
just ansible::playbook services --tags all --limit vps --check --diff
just ansible::playbook services --tags all --limit vps
```

## 5. One-time setup

- **Semaphore**: see [manual-setup.md](manual-setup.md). If `/opt/data/semaphore` was restored, its Key Store decrypts with the same `SEMAPHORE_ACCESS_KEY_ENCRYPTION` and nothing needs doing. Otherwise follow the setup at the top of `ansible/services/semaphore.yaml`. Either way, the SSH key in its Key Store must be in the new `root`'s `authorized_keys`.
- **aven**: only on a fresh database. Run the setup at the top of `ansible/services/aven.yaml`.
- Watch Gatus for the next hourly restic heartbeat.
