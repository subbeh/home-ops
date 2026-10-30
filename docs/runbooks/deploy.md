---
covers:
  - ansible/roles/services/tasks/main.yaml
  - ansible/playbooks/services.yaml
  - ansible/mod.just
---
# Deploy Services by hand

Hand edits to Services, the role, `group_vars` or the inventory are never Auto-deployed. Deploy them from the laptop. You need the mise env, with `BWS_ACCESS_TOKEN` loaded from `.env`, and the tailnet up.

```sh
# Preview first: what would change, without changing it
just ansible::playbook services --tags karakeep --check --diff

# Deploy
just ansible::playbook services --tags karakeep
```

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

## Connectivity check

```sh
just ansible::playbook test-connection --limit vps
```
