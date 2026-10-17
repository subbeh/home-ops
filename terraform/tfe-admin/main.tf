# Creates the VCS-driven workspaces for the other stacks and their secrets, read from
# Bitwarden Secrets Manager so it stays the only place they live. Runs on the laptop
# (execution mode Local, state in TFC) with `just tf::apply tfe-admin`.
#
# Bootstrap, once:
#   1. Install the HCP Terraform GitHub App on subbeh/home-ops.
#   2. `terraform login`, then `terraform -chdir=terraform/tfe-admin init` creates this workspace.
#   3. Set its Execution Mode to Local in the TFC UI, then `just tf::apply tfe-admin`.
terraform {
  required_version = ">= 1.13"

  required_providers {
    tfe = {
      source  = "hashicorp/tfe"
      version = "~> 0.82"
    }
    bitwarden-secrets = {
      source  = "bitwarden/bitwarden-secrets"
      version = "~> 1.0"
    }
  }

  cloud {
    organization = "sbbh-cloud"
    workspaces {
      name = "tfe-admin"
    }
  }
}

# Uses the `terraform login` token.
provider "tfe" {
  organization = "sbbh-cloud"
}

# BW_ACCESS_TOKEN and BW_ORGANIZATION_ID are set by terraform/mod.just.
provider "bitwarden-secrets" {
  api_url      = "https://api.bitwarden.com"
  identity_url = "https://identity.bitwarden.com"
}

locals {
  # Each workspace runs terraform/<name> from main. env maps variable => Bitwarden secret key.
  workspaces = {
    cloudflare = {
      auto_apply = true
      env        = { CLOUDFLARE_API_TOKEN = "CLOUDFLARE_API_TOKEN" }
    }
    # Confirmed by hand: a bad policy can cut off the tailnet.
    tailscale = {
      auto_apply = false
      env = {
        TAILSCALE_OAUTH_CLIENT_ID     = "TAILSCALE_TERRAFORM_OAUTH_CLIENT_ID"
        TAILSCALE_OAUTH_CLIENT_SECRET = "TAILSCALE_TERRAFORM_OAUTH_CLIENT_SECRET"
      }
    }
  }

  env = merge([
    for ws, cfg in local.workspaces : {
      for name, key in cfg.env : "${ws}/${name}" => { workspace = ws, name = name, key = key }
    }
  ]...)

  secret_ids = { for s in data.bitwarden-secrets_list_secrets.all.secrets : s.key => s.id }
}

data "tfe_github_app_installation" "github" {
  name = "subbeh"
}

resource "tfe_workspace" "stack" {
  for_each = local.workspaces

  name              = each.key
  working_directory = "terraform/${each.key}"
  auto_apply        = each.value.auto_apply
  terraform_version = "~> 1.16"
  # Nothing runs until the next push touches the stack.
  queue_all_runs = false

  vcs_repo {
    identifier                 = "subbeh/home-ops"
    branch                     = "main"
    github_app_installation_id = data.tfe_github_app_installation.github.id
  }
}

data "bitwarden-secrets_list_secrets" "all" {}

data "bitwarden-secrets_secret" "env" {
  for_each = local.env
  id       = local.secret_ids[each.value.key]
}

resource "tfe_variable" "env" {
  for_each = local.env

  workspace_id = tfe_workspace.stack[each.value.workspace].id
  category     = "env"
  key          = each.value.name
  value        = data.bitwarden-secrets_secret.env[each.key].value
  sensitive    = true
}
