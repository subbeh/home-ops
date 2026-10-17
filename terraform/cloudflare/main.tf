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

# Adopts the record created back when state was local; delete once applied in TFC.
import {
  to = cloudflare_dns_record.vps_wildcard
  id = "288a97239d2617df3bc3a411528dd23f/1948850fc1cbf53c7779fbc0652af7c1"
}

# DNS-only, pointing at the VPS's Tailscale IP: the names resolve publicly but only
# connect from the tailnet. Traefik's wildcard cert comes from a DNS-01 challenge,
# so nothing needs to be reachable from the internet.
resource "cloudflare_dns_record" "vps_wildcard" {
  zone_id = data.cloudflare_zone.sbbh_cloud.zone_id
  name    = "*.vps.sbbh.cloud"
  type    = "A"
  content = "100.77.96.125"
  proxied = false
  ttl     = 1
}
