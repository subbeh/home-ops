terraform {
  required_version = ">= 1.13"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.0"
    }
  }
}

# Reads CLOUDFLARE_API_TOKEN from the environment.
provider "cloudflare" {}

data "cloudflare_zone" "sbbh_cloud" {
  filter = {
    name = "sbbh.cloud"
  }
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
