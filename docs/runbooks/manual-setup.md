---
covers:
  - ansible/services/semaphore.yaml
  - terraform/tfe-admin/main.tf
  - terraform/tailscale/main.tf
  - .github/workflows/deploy.yaml
---
# Manual setup

Everything that can't live in this repo: clicks in web consoles, values that are created once, and their order. Do these after a rebuild, or when a credential is lost. Checked items are done on the current setup.

## Laptop

- [x] `~/.ssh/config` matches the inventory's `ansible_host`: `Host vps vps.sbbh.cloud vps.tailnet-7233.ts.net`, with the home-ops key and `User root`.
- [x] `BWS_ACCESS_TOKEN` in `.env`, from the laptop's Bitwarden machine account.

## Bitwarden

Secrets reach Secrets Manager through `.bws.yaml`: each key points at a vault item field, and the dotfiles sync (`.matescripts/70-bws-sync.sh`) copies it over. For every secret below, create the vault item field, add the key to `.bws.yaml`, and run the sync.

- [x] `SEMAPHORE_ADMIN_PASSWORD`
- [x] `SEMAPHORE_ACCESS_KEY_ENCRYPTION`: `head -c32 /dev/urandom | base64` (44 characters). Never change it once Semaphore holds keys: its Key Store becomes unreadable.
- [x] `SEMAPHORE_BWS_ACCESS_TOKEN`: Secrets Manager → Machine accounts → New (`semaphore`) → Projects: Can read on the Service secrets → Access tokens → Create.
- [x] `TAILSCALE_TERRAFORM_OAUTH_CLIENT_ID` / `_SECRET`: see Tailscale below.
- [x] `SEMAPHORE_API_TOKEN`: see Semaphore below.

## Tailscale

- [x] Seed `terraform/tailscale/policy.hujson` from the admin console's policy (only when the tailnet existed before this repo managed it).
- [ ] OAuth client for Terraform: Settings → OAuth clients → Generate, scopes **Policy File: Write**, **OAuth Keys: Write** and **Auth Keys: Write** with tag `tag:ci`. The `tailscale` stack creates the CI client, and an OAuth client can only grant scopes and tags it holds itself (otherwise: `actor cannot set scopes (403)`). `tag:ci` only exists once the policy is applied, so on a fresh tailnet apply the policy first, then add Auth Keys.

## Semaphore

After `just ansible::playbook services --tags semaphore`, at `https://semaphore.vps.sbbh.cloud` (login `admin`, `SEMAPHORE_ADMIN_PASSWORD`). The same steps are at the top of `ansible/services/semaphore.yaml`.

- [x] Project settings: max parallel tasks 1.
- [x] Key Store: an SSH key whose public half is in root's `authorized_keys` on the VPS.
- [x] Repository: `https://github.com/subbeh/home-ops.git`, branch `main`.
- [x] Inventory: File, `ansible/inventory.yml`, **User Credentials**: the SSH key. Without it the task can't log in.
- [x] Variable group: an empty one.
- [x] Template `services`: playbook `ansible/playbooks/services.yaml`, Ansible prompts: Tags. Its project and template IDs are in `.github/workflows/deploy.yaml`.
- [x] API token (User → Tokens) → `SEMAPHORE_API_TOKEN` in `.bws.yaml`.

## Terraform Cloud

Org `sbbh-cloud`.

- [x] Install the HCP Terraform GitHub App (https://github.com/apps/terraform-cloud) on the personal account `subbeh`, only `home-ops`.
- [x] User Settings → Tokens → GitHub App OAuth Token: create and authorize it. No organization grants needed. `tfe-admin` finds the installation by name through it.
- [x] User API token (User Settings → Tokens) → `TFC_API_TOKEN` in `.bws.yaml`. No `terraform login`: the `just tf::` recipes export it for Terraform and the tfe provider.
- [x] `just tf::init tfe-admin` (creates the `tfe-admin` workspace).
- [x] `tfe-admin` workspace → Settings → General → Execution Mode: **Local**.
- [x] `just tf::apply tfe-admin`: creates the `cloudflare` and `tailscale` workspaces and `SEMAPHORE_API_TOKEN` in GitHub.
- [ ] `tailscale` workspace: start a run (workspaces don't run on creation) and **Confirm** it. Adds `tag:ci` and creates the CI client.
- [ ] `just tf::apply tfe-admin` again: copies the CI client into GitHub as `TS_OAUTH_CLIENT_ID` / `TS_OAUTH_SECRET`.
- [ ] `cloudflare` workspace: start a run; it imports the existing wildcard record. Then delete the `import` block in `terraform/cloudflare/main.tf` and the laptop's old `terraform/cloudflare/terraform.tfstate`.

## Renovate

- [ ] Install the Mend Renovate GitHub App on `subbeh/home-ops`. Its first PRs pin every image digest.
