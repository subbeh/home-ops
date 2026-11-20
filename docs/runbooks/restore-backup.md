---
covers:
  - ansible/services/restic.yaml
  - ansible/services/backrest.yaml
  - ansible/services/tasks/restic-sqlite-copies.yaml
  - ansible/services/data/restic/**
---
# Restore Service data from restic

The repository is `sftp:storagebox:restic/vps` on a Hetzner Storage Box sub-account. Its credentials are in Bitwarden Secrets Manager: `RESTIC_VPS_SSH_USER`, `RESTIC_VPS_SSH_KEY` and `RESTIC_VPS_PASSWORD`. Snapshot paths start with `/data/`, which is `/opt/data` on the Host (e.g. `/data/karakeep`), or `/workspace/`, which is `/opt/workspace`. Snapshots from before the workspace moved hold it at `/data/syncthing/data/workspace`.

> TODO(you): none of the restore commands below have been run end to end yet. Run them once against a test path and fix this page.

## Look around

Backrest (https://backups.vps.sbbh.cloud) browses the snapshots and downloads single files or folders.

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

3. Swap the data in: `mv /opt/data/<service> /opt/data/<service>.old && mv /opt/restore/data/<service> /opt/data/`. A SQLite db in it may be torn, so replace each with its copy as in [Restore a SQLite db](#restore-a-sqlite-db).
4. Deploy the Service again ([deploy.md](deploy.md)). This fixes ownership of the files it manages and starts the containers.
5. Once it works, remove `/opt/data/<service>.old` and `/opt/restore`.

## Restore a SQLite db

A file copy of a live SQLite db can catch it and its `-wal` at different moments. So at :55 a root cron on the Host (`/usr/local/sbin/restic-sqlite-copies`, from `ansible/services/tasks/restic-sqlite-copies.yaml`) writes a consistent copy of every `*.db`, `*.sqlite` and `*.sqlite3` under `/opt/data` to `/opt/data/restic/sqlite/<same path>`, and the backup on the hour picks them up. It skips syncthing's synced files and the `.pki` cert stores in Hermes's homes. Each run pushes to the `backups/sqlite-copies` heartbeat in Gatus, naming any db it failed to copy, and logs to the journal (`journalctl -t restic-sqlite-copies`).

1. Stop the Service's containers: `docker stop <container>...`.
2. Restore the copy into a scratch directory with the one-off container from [Restore one Service](#restore-one-service), using `--include /data/restic/sqlite/<path>`, where `<path>` is the db's path under `/opt/data` (e.g. `karakeep/data/db.db`).
3. Check it: `sqlite3 /opt/restore/data/restic/sqlite/<path> 'PRAGMA integrity_check'` prints `ok`.
4. Replace the live db. Remove its `-wal` and `-shm` first: they belong to the old file. `cat` keeps the live file's owner and mode:

   ```sh
   rm -f /opt/data/<path>-wal /opt/data/<path>-shm
   cat /opt/restore/data/restic/sqlite/<path> > /opt/data/<path>
   ```

5. Start the containers again (`docker start <container>...`) and remove `/opt/restore`.

## Restore everything (new VPS)

Follow [rebuild-vps.md](rebuild-vps.md). Restore **before** the restic Service's containers first start, or an empty `/opt/data` starts getting backed up.
