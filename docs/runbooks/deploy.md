---
covers:
  - ansible/roles/services/tasks/main.yaml
  - ansible/playbooks/services.yaml
  - ansible/mod.just
  - ansible/playbooks/hosts.yaml
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
- A Service assigned to more than one Host needs `--limit <host>`.
- Every Deploy pulls images and **recreates** the selected containers, even when nothing changed.
- Every Deploy that touches containers then removes every image no container uses (`docker image prune -a`), so a stopped Service's image is re-pulled on its next Deploy.

## Special cases

- **semaphore**: always deployed by hand, with `--tags semaphore`, and never while an Auto-deploy task is running, since recreating it kills the task.
- **traefik**: every Service's URL is briefly down while it's recreated.
- **New Service with secrets**: add the secrets to `.bws.yaml` first, which the dotfiles bws sync creates in Secrets Manager; the role fails on any missing `bws_secrets.<KEY>`.
- **Rollback**: revert the commit, then deploy the Service again.

## Host packages

`playbooks/hosts.yaml` installs the core packages in `ansible/group_vars/debian.yaml` (curl, dig, iperf3, tmux, tcpdump, ...) on every Host in the `debian` group, so a new Host gets them too. Packages a role needs for itself stay in that role. It never runs as an Auto-deploy. The iperf3 package is preseeded not to start its server daemon.

It also gives root a shell alias block in `~/.bashrc` (`ll`, `la`, `..`, `ports`, colour for grep/ip/diff) and a `~/.tmux.conf` (`ansible/playbooks/files/tmux.conf`) with the laptop's core keys and prefix `C-s` and an amber status bar naming the Host. Nested in the laptop's tmux, `C-s C-s <key>` drives the Host's; the laptop keeps `C-h`/`C-l`, so switch the Host's windows with `n`/`p`.

```sh
just ansible::playbook hosts --check --diff
just ansible::playbook hosts
```

## Connectivity check

```sh
just ansible::playbook test-connection --limit vps
```
