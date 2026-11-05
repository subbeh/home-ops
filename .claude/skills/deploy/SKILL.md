---
name: deploy
description: Deploy Services to Hosts with the services playbook, or preview a Deploy in check mode. Use when asked to deploy, roll out, redeploy or restart a Service.
covers:
  - ansible/roles/services/tasks/main.yaml
  - ansible/mod.just
  - .github/workflows/deploy.yaml
---
# Deploy

[docs/runbooks/deploy.md](../../../docs/runbooks/deploy.md) is the reference: tag selection, `--limit`, and the special cases (semaphore, traefik, rollback). Read it first.

## Steps

1. **Scope**: work out which Services changed and which Hosts they're assigned to (`docs/hosts.md`). A Service on more than one Host needs `--limit <host>`.
2. **Preview**: run `just ansible::playbook services --tags <services> [--limit <host>] --check --diff`. Done when it ends with no failed tasks. Summarize the changes for the user; Services with `no_log` show none, so say so.
3. **Leases**: when `agent-manager` is on PATH, run `agent-manager reservations` and look for `live/<host>/<service>` on each selected Service. A holder is another session changing that Service live: name it and its note when you ask for the go-ahead, and ask even when the Deploy was already asked for.
4. **Deploy**: only when the user asked for a real Deploy in the current turn. `/deploy <services>` is that ask; `--check` or "preview" means stop after step 2. Run the same command without `--check --diff`, and report the recap.

## Gotchas

- **Real runs need clean main**: the recipe refuses a real run unless the tree is clean and `HEAD` is local `main`. From a worktree, land first, then Deploy from the main checkout; preview with `--check` from anywhere. Use `DEPLOY_FROM_BRANCH=1` only when the user asks for it.
- **Each run recreates** every selected container, even when the preview shows no changes.
- **semaphore**: deploy it by hand, and only when no Auto-deploy task is running. Auto-deploys never cover it.
- **Hand edits** never Auto-deploy; only merged Renovate Version Bumps do. After merging a hand edit, the user still needs a Deploy.
