terraform {
  required_version = ">= 1.13"

  required_providers {
    tailscale = {
      source  = "tailscale/tailscale"
      version = "~> 0.29"
    }
  }

  cloud {
    organization = "sbbh-cloud"
    workspaces {
      name = "tailscale"
    }
  }
}

# Reads TAILSCALE_OAUTH_CLIENT_ID and TAILSCALE_OAUTH_CLIENT_SECRET from the
# workspace (see terraform/tfe-admin). The client needs policy_file and oauth_keys, plus
# auth_keys with tag:ci: Tailscale only lets it grant scopes and tags it holds itself.
provider "tailscale" {}

# Owns the whole tailnet policy file; edit policy.hujson, never the admin console.
resource "tailscale_acl" "policy" {
  acl = file("${path.module}/policy.hujson")
  # Seeded from the live policy, so no import is needed.
  overwrite_existing_content = true
}

# For .github/workflows/deploy.yaml; terraform/tfe-admin copies it into GitHub secrets.
resource "tailscale_oauth_client" "ci" {
  scopes = ["auth_keys"]
  tags   = ["tag:ci"]
  # tag:ci only exists once the policy defines it.
  depends_on = [tailscale_acl.policy]
}

output "ci_oauth_client_id" {
  value = tailscale_oauth_client.ci.id
}

output "ci_oauth_client_secret" {
  value     = tailscale_oauth_client.ci.key
  sensitive = true
}
