# DNS records in the sbbh.cloud zone (see the `records` variable in main.tf), except
# vps_wildcard, which main.tf builds from network.yaml.
records = {
  # OPNsense's Tailscale IP: its UI and SSH are open on the tailnet only, never the WAN.
  opnsense = { name = "opnsense.sbbh.cloud", type = "A", content = "100.66.175.26" }
  # jetkvm's address on the upstream Network (network.yaml); resolves publicly, connects only on that LAN.
  jetkvm = { name = "kvm.sbbh.cloud", type = "A", content = "192.168.11.11" }
}
