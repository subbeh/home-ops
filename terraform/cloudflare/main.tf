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

# All records, set in records.auto.tfvars (TFC loads *.auto.tfvars on VCS runs).
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

resource "cloudflare_dns_record" "extra" {
  for_each = var.records

  zone_id = data.cloudflare_zone.sbbh_cloud.zone_id
  name    = each.value.name
  type    = each.value.type
  content = each.value.content
  proxied = each.value.proxied
  ttl     = each.value.ttl
}
