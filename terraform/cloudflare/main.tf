terraform {
  required_version = ">= 1.13"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.0"
    }
  }

  cloud {
    organization = "sbbh-cloud"
    workspaces {
      name = "cloudflare"
    }
  }
}

# Reads CLOUDFLARE_API_TOKEN from the workspace (see terraform/tfe-admin).
provider "cloudflare" {}

data "cloudflare_zone" "sbbh_cloud" {
  filter = {
    name = "sbbh.cloud"
  }
}

# The wildcard used to be its own resource; this keeps it from being destroyed and recreated.
moved {
  from = cloudflare_dns_record.vps_wildcard
  to   = cloudflare_dns_record.extra["vps_wildcard"]
}

# Records set in records.auto.tfvars (TFC loads *.auto.tfvars on VCS runs); local.records adds vps_wildcard.
# Keyed by a stable label, so renaming a key replaces the record.
variable "records" {
  type = map(object({
    name    = string
    type    = string
    content = string
    proxied = optional(bool, false)
    ttl     = optional(number, 1)
  }))
  default = {}
}

locals {
  network = yamldecode(file("${path.module}/../../ansible/group_vars/all/network.yaml"))
  # DNS-only, pointing at the VPS's Tailscale IP: the names resolve publicly but only
  # connect from the tailnet. Traefik's wildcard cert comes from a DNS-01 challenge,
  # so nothing needs to be reachable from the internet.
  records = merge(var.records, {
    vps_wildcard = { name = "*.vps.sbbh.cloud", type = "A", content = local.network.networks.tailnet.addresses.vps, proxied = false, ttl = 1 }
  })
}

resource "cloudflare_dns_record" "extra" {
  for_each = local.records

  zone_id = data.cloudflare_zone.sbbh_cloud.zone_id
  name    = each.value.name
  type    = each.value.type
  content = each.value.content
  proxied = each.value.proxied
  ttl     = each.value.ttl
}
