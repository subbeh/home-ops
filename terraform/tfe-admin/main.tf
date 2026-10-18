# Creates the VCS-driven workspaces for the other stacks and their secrets, plus the
# deploy workflow's GitHub secrets, read from Bitwarden Secrets Manager (or, for the
# Tailscale CI client, the tailscale workspace) so nothing is copied by hand. Runs on the laptop
# (execution mode Local, state in TFC) with `just tf::apply tfe-admin`.
#
# Bootstrap, once:
#   1. Install the HCP Terraform GitHub App on subbeh/home-ops.
#   2. A TFC user API token in Bitwarden as TFC_API_TOKEN, then `just tf::init tfe-admin`
#      creates this workspace.
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
    github = {
      source  = "integrations/github"
      version = "~> 6.13"
    }
  }

  cloud {
    organization = "sbbh-cloud"
    workspaces {
      name = "tfe-admin"
    }
  }
}

# TFE_TOKEN is set by terraform/mod.just.
provider "tfe" {
  organization = "sbbh-cloud"
}

# BW_ACCESS_TOKEN and BW_ORGANIZATION_ID are set by terraform/mod.just.
provider "bitwarden-secrets" {
  api_url      = "https://api.bitwarden.com"
  identity_url = "https://identity.bitwarden.com"
}

# GITHUB_TOKEN is set by terraform/mod.just.
provider "github" {
  owner = "subbeh"
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

# Deploy workflow secrets (.github/workflows/deploy.yaml).
data "bitwarden-secrets_secret" "semaphore_api_token" {
  id = local.secret_ids["SEMAPHORE_API_TOKEN"]
}

resource "github_actions_secret" "semaphore_api_token" {
  repository  = "home-ops"
  secret_name = "SEMAPHORE_API_TOKEN"
  value       = data.bitwarden-secrets_secret.semaphore_api_token.value
}

# The tailscale workspace only has its CI client after its first apply, so the
# first `just tf::apply tfe-admin` skips these; run it again once tailscale applied.
data "tfe_workspace_ids" "all" {
  names = ["*"]
}

data "tfe_outputs" "tailscale" {
  count     = contains(keys(data.tfe_workspace_ids.all.ids), "tailscale") ? 1 : 0
  workspace = "tailscale"
}

locals {
  ts_ci_client_id = try(data.tfe_outputs.tailscale[0].nonsensitive_values.ci_oauth_client_id, null)
}

resource "github_actions_secret" "ts_oauth_client_id" {
  count       = local.ts_ci_client_id == null ? 0 : 1
  repository  = "home-ops"
  secret_name = "TS_OAUTH_CLIENT_ID"
  value       = local.ts_ci_client_id
}

resource "github_actions_secret" "ts_oauth_secret" {
  count       = local.ts_ci_client_id == null ? 0 : 1
  repository  = "home-ops"
  secret_name = "TS_OAUTH_SECRET"
  value       = data.tfe_outputs.tailscale[0].values.ci_oauth_client_secret
}
