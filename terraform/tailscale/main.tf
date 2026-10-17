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
# workspace (see terraform/tfe-admin); the client needs the policy_file scope.
provider "tailscale" {}

# Owns the whole tailnet policy file; edit policy.hujson, never the admin console.
resource "tailscale_acl" "policy" {
  acl = file("${path.module}/policy.hujson")
  # Seeded from the live policy, so no import is needed.
  overwrite_existing_content = true
}
