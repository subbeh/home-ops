terraform {
  required_version = ">= 1.13"

  required_providers {
    tailscale = {
      source  = "tailscale/tailscale"
      version = "~> 0.30"
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
# workspace (see terraform/tfe-admin). The client needs policy_file, oauth_keys and dns, plus
# auth_keys with tag:ci: Tailscale only lets it grant scopes and tags it holds itself.
provider "tailscale" {}

# Owns the whole tailnet policy file; edit policy.hujson, never the admin console.
# hosts.vps and the routes come from network.yaml, the only place they are written.
locals {
  network = yamldecode(file("${path.module}/../../ansible/group_vars/all/network.yaml"))
}

resource "tailscale_acl" "policy" {
  acl = templatefile("${path.module}/policy.hujson", {
    vps    = local.network.networks.tailnet.addresses.vps
    routes = local.network.tailnet_routes
  })
  # Seeded from the live policy, so no import is needed.
  overwrite_existing_content = true
}

# Tailnet devices resolve the home names through OPNsense's Unbound, which holds every record,
# at home and away (over its 10.11.0.0/16 subnet route); public DNS has none.
# svc.sbbh.cloud is ingress_domain in services.yaml.
resource "tailscale_dns_split_nameservers" "home" {
  for_each    = toset([local.network.home_domain, "svc.sbbh.cloud"])
  domain      = each.key
  nameservers = [local.network.networks.servers.addresses.opnsense]
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
