---
covers:
  - ansible/services/restic.yaml
  - ansible/services/backrest.yaml
---
# Restore Service data from restic

The repository is `sftp:storagebox:restic/vps` on a Hetzner Storage Box sub-account. Its credentials are in Bitwarden Secrets Manager: `RESTIC_VPS_SSH_USER`, `RESTIC_VPS_SSH_KEY` and `RESTIC_VPS_PASSWORD`. Snapshot paths start with `/data/`, which is `/opt/data` on the Host (e.g. `/data/karakeep`).

> TODO(you): none of the restore commands below have been run end to end yet. Run them once against a test path and fix this page.

## Look around

Backrest (https://backrest.vps.sbbh.cloud) browses the snapshots and downloads single files or folders.

From the shell, the running `restic-backup` container already has the repository, password and SSH setup:

```sh
docker exec restic-backup restic snapshots
docker exec restic-backup restic ls latest /data/<service>
```

## Restore one Service

1. Stop the Service's containers so they don't write while you restore: `docker stop <container>...`.
2. Restore into a scratch directory. `restic-backup` mounts `/opt/data` read-only, so use a one-off container that mounts the SSH setup and a writable target:

   ```sh
   docker run --rm --entrypoint restic \
     -e RESTIC_REPOSITORY=sftp:storagebox:restic/vps \
     -e RESTIC_PASSWORD="$(bws secret list -o json | jq -r '.[] | select(.key=="RESTIC_VPS_PASSWORD").value')" \
     -v /opt/data/restic/ssh:/run/secrets/.ssh \
     -v /opt/data/restic/ssh/config:/root/.ssh/config:ro \
     -v /opt/restore:/restore \
     mazzolino/restic:<version from restic.yaml> \
     restore latest --include /data/<service> --target /restore
   ```

   > TODO(you): confirm that `/root/.ssh/config` is where ssh in this image looks, and that `bws` is available on the VPS (otherwise paste the password).

3. Swap the data in: `mv /opt/data/<service> /opt/data/<service>.old && mv /opt/restore/data/<service> /opt/data/`.
4. Deploy the Service again ([deploy.md](deploy.md)). This fixes ownership of the files it manages and starts the containers.
5. Once it works, remove `/opt/data/<service>.old` and `/opt/restore`.

## Restore everything (new VPS)

Follow [rebuild-vps.md](rebuild-vps.md). Restore **before** the restic Service's containers first start, or an empty `/opt/data` starts getting backed up.
