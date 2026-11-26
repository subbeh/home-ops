---
covers:
  - ansible/roles/services/tasks/main.yaml
  - ansible/playbooks/services.yaml
  - ansible/mod.just
  - ansible/playbooks/hosts.yaml
  - ansible/playbooks/hosts-update.yaml
  - ansible/group_vars/debian.yaml
  - ansible/playbooks/files/tmux.conf
---
# Deploy Services by hand

Hand edits to Services, the role, `group_vars` or the inventory are never Auto-deployed. Deploy them from the laptop. You need the mise env, with `BWS_ACCESS_TOKEN` loaded from `.env`, and the tailnet up.

```sh
# Preview first: what would change, without changing it
just ansible::playbook services --tags karakeep --check --diff

# Deploy
just ansible::playbook services --tags karakeep
```

A real run (no `--check`) refuses unless the tree is clean and `HEAD` is local `main`: a run from a stale or unlanded tree silently undoes what main last deployed. `DEPLOY_FROM_BRANCH=1` overrides it.

## Selecting what runs

| Tags | Runs |
|---|---|
| `--tags <service>[,<service>]` | those Services, on the Hosts they're assigned to |
| `--tags <service>,<step>` | only those Steps: `pre-tasks`, `files`, `containers`, `post-tasks` |
| `--tags all` (or no tags) | every Service assigned to each Host |

- A tag that is neither a Service nor a Step fails the run (typo protection). So does a Step tag on its own.
- Selecting a Service assigned to more than one Host (today only restic, and so every `--tags all` run) needs `--limit <host>`. Single-Host Services on different Hosts run together without it.
- Every Deploy pulls images and **recreates** the selected containers, even when nothing changed.
- Every Deploy that touches containers then removes, by ID, every image no container (running or stopped) was created from, so a removed Service's image is re-pulled on its next Deploy. Not `docker image prune -a`: with the containerd image store it keeps an old image whose tag a container's `tag@digest` reference still names.

## Special cases

- **semaphore**: always deployed by hand, with `--tags semaphore`, and never while an Auto-deploy task is running, since recreating it kills the task.
- **traefik**: every Service's URL is briefly down while it's recreated.
- **New Service with secrets**: add the secrets to `.bws.yaml` first, which the dotfiles bws sync creates in Secrets Manager; the role fails on any missing `bws_secrets.<KEY>`.
- **Rollback**: revert the commit, then deploy the Service again.

## Host packages

`playbooks/hosts.yaml` installs the core packages in `ansible/group_vars/debian.yaml` (curl, dig, iperf3, tmux, tcpdump, ...) on every Host in the `debian` group, so a new Host gets them too. Packages a role needs for itself stay in that role. It never runs as an Auto-deploy. It runs the packaged iperf3 server on `5201` on each box, so not on the LXC guests (nas-svc, nuc-svc), which share their node's NIC. A drop-in binds it to the Host's servers address, or on the vps its tailnet address, so it never listens on a public address; the package is preseeded not to start the server itself, so a fresh install doesn't listen everywhere before the drop-in lands. It also authorizes Semaphore's SSH key (`SEMAPHORE_SSH_PUBLIC_KEY`) for each Host's `ansible_user`, so the `hosts-update` template can reach every Host; that needs `BWS_ACCESS_TOKEN`, like a Service Deploy.

It also gives root a shell alias block in `~/.bashrc` (`ll`, `la`, `..`, `ports`, colour for grep/ip/diff, and an `mv` that refuses to replace an existing file, with an error and exit 1) and a `~/.tmux.conf` (`ansible/playbooks/files/tmux.conf`) with the laptop's core keys and prefix `C-s` and an amber status bar naming the Host. Nested in the laptop's tmux, `C-s C-s <key>` drives the Host's; the laptop keeps `C-h`/`C-l`, so switch the Host's windows with `n`/`p`.

```sh
just ansible::playbook hosts --check --diff
just ansible::playbook hosts
```

## Host updates

`playbooks/hosts-update.yaml` runs `apt` update, dist-upgrade and autoremove on every Host in the `debian` group, one Host at a time with the vps last, and reboots a Host only when `/var/run/reboot-required` exists (Ubuntu's update-notifier creates it) or `/boot` holds a newer kernel than the running one (nothing creates that file on Debian). LXCs have no kernel of their own, so they never reboot for one. The vps runs Semaphore, so it gets `shutdown -r +1` instead of a waited-on reboot, and the task ends green before the vps goes down. The upgrade runs detached from SSH, so it finishes even when upgrading docker-ce restarts the Semaphore container mid-task; that task ends red, so re-run it or check Gatus. Other OS families aren't covered yet. Nothing schedules it: start the Semaphore template `hosts-update` (pick a Host under Limit), or run it from the laptop. Gatus alerts if an update breaks a Service.

```sh
just ansible::playbook hosts-update --limit vps --check --diff
just ansible::playbook hosts-update --limit vps
```

## Connectivity check

```sh
just ansible::playbook test-connection --limit vps
```
