---
covers:
  - terraform/mod.just
  - terraform/tfe-admin/main.tf
---
# Terraform

Each directory in `terraform/` is a stack with its state in Terraform Cloud (org `sbbh-cloud`, one workspace per stack, named after it). [terraform-stacks.md](terraform-stacks.md) lists them.

## How stacks run

- **VCS-driven stacks** run in TFC from `main`. PRs get speculative plans, which post their own PR checks; merging applies.
  - `cloudflare` applies automatically.
  - `tailscale` waits for a manual confirm in the TFC UI, since a bad policy can cut off the tailnet.
- **`tfe-admin`** creates those workspaces and their sensitive env vars. It runs on the laptop (execution mode Local, state in TFC):

  ```sh
  just tf::apply tfe-admin
  ```

  The recipe sets `BW_ACCESS_TOKEN` and `BW_ORGANIZATION_ID` for the Bitwarden provider from your `BWS_ACCESS_TOKEN`. The one-time bootstrap is at the top of `terraform/tfe-admin/main.tf`.

## Secrets

Workspaces read provider credentials from env vars that `tfe-admin` copies from Bitwarden Secrets Manager. The mapping is the `env` map in `locals.workspaces`, from variable name to Bitwarden key. To rotate a secret, change it in Bitwarden, then run `just tf::apply tfe-admin`.

## Adding a stack

1. Create `terraform/<name>/main.tf` with a `cloud` block, org `sbbh-cloud`, workspace `<name>`.
2. Add `<name>` to `locals.workspaces` in `terraform/tfe-admin/main.tf`, with `auto_apply` and its `env` secrets.
3. Run `just tf::apply tfe-admin`, then push. The workspace runs nothing until a push touches the stack (`queue_all_runs = false`).
4. Run `just docs`.
