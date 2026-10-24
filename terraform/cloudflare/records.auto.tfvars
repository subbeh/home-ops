# DNS records in the sbbh.cloud zone (see the `records` variable in main.tf).
records = {
  # DNS-only, pointing at the VPS's Tailscale IP: the names resolve publicly but only
  # connect from the tailnet. Traefik's wildcard cert comes from a DNS-01 challenge,
  # so nothing needs to be reachable from the internet.
  vps_wildcard = { name = "*.vps.sbbh.cloud", type = "A", content = "100.77.96.125" }
  # jetkvm's address on the upstream Network (network.yaml); resolves publicly, connects only on that LAN.
  jetkvm = { name = "kvm.sbbh.cloud", type = "A", content = "192.168.11.11" }
}
