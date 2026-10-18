---
covers:
  - .github/workflows/**
  - .renovaterc.json5
  - .renovate/**
  - ansible/services/semaphore.yaml
  - ansible/services/tasks/semaphore-bws.yaml
---
# Automation

The rationale is in [ADR 0001](adr/0001-auto-deploy-via-semaphore-over-tailscale.md).

## Renovate

The hosted Mend Renovate GitHub App reads `.renovaterc.json5`, which extends the presets in `.renovate/`. Commits are semantic (`fix(container): update image x ( a ➔ b )`), and there's a dependency dashboard issue.

| Target | Found by | Automerge |
|---|---|---|
| Service images (`ansible/services/*.yaml`) | custom regex manager on `image:`, digests pinned | patch + digest, as a PR, after 3 days |
| Semaphore (image and annotated `bws` version) | same, plus the annotated-dependency regex manager | never |
| GitHub Actions | built-in, digests pinned | minor, patch and digest, as a PR, after 3 days |
| Terraform providers | built-in; lock files refreshed monthly | minor + patch, as a PR |
| mise tools (`.mise/config.toml`) | built-in | minor + patch, straight to `main` (no PR, no checks: those only run on PRs) |

Anything not listed (e.g. minor or major image bumps) waits for a manual merge. To annotate a pinned version so Renovate tracks it, put this comment on the line above the version:

```yaml
# renovate: datasource=github-releases depName=owner/repo
```

## PR check (`.github/workflows/check.yaml`)

The check uses no secrets and runs with only `ANSIBLE_CONFIG=ansible/ansible.cfg` set (no mise), the same as Semaphore. It runs:

1. A syntax check of the services playbook.
2. A load of every Service definition (the syntax check never parses them).
3. A check that the generated docs are current.
4. `renovate-config-validator --strict`.

## Auto-deploy (`.github/workflows/deploy.yaml`)

Only merged Renovate Version Bumps Auto-deploy. Hand edits are always deployed by hand ([runbooks/deploy.md](runbooks/deploy.md)).

1. A push to `main` that touches `ansible/services/*.yaml` starts the workflow.
2. It continues only if the commit belongs to a PR opened by `renovate[bot]`. The Services to deploy are that PR's changed Service files, minus `semaphore`.
3. It joins the tailnet as an ephemeral `tag:ci` node and starts a Semaphore task with those Services as tags.
4. It polls until the task succeeds or fails, and mirrors the result. Only the status and the task link are logged (the repo is public); the output stays in Semaphore.

Known limits:

- A Service assigned to more than one Host makes the run fail, since the playbook then requires `--limit`.
- Semaphore clones `main` when the task starts, so a push that lands in between rides along.
- There's no automatic rollback: revert the PR and deploy by hand.

GitHub secrets it needs, all written by `terraform/tfe-admin` ([terraform.md](terraform.md)):

- `TS_OAUTH_CLIENT_ID`, `TS_OAUTH_SECRET`: the `tag:ci` OAuth client, created by the `tailscale` stack.
- `SEMAPHORE_API_TOKEN`: from Bitwarden.

The Semaphore project and template IDs aren't secret; they're in the workflow's `env`.

## Semaphore

Semaphore runs the services playbook for Auto-deploys, at `https://semaphore.vps.sbbh.cloud`.

- It's never Auto-deployed itself: recreating its container would kill the running task. Deploy it by hand with `--tags semaphore`. Its Renovate PRs never automerge.
- It runs one task at a time, so concurrent Auto-deploys queue.
- The image has no `bws`, so a pre-task installs the pinned musl build into `/opt/data/semaphore/bin`.
- Tasks don't inherit the container's env. `BWS_ACCESS_TOKEN` (Bitwarden `SEMAPHORE_BWS_ACCESS_TOKEN`, from a dedicated machine account) is forwarded to them, and `ANSIBLE_CONFIG` is set for them, both on the container, so the variable group stays empty.
- The one-time UI setup (key, repo, inventory, variable group, template, API token) is at the top of `ansible/services/semaphore.yaml`.
