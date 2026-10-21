# OPNsense runs bare metal and is configured by Ansible (oxlorg.opnsense)

OPNsense runs directly on a dedicated Topton N5105, not as a Proxmox VM as in the archived setup, so the home network no longer goes down with the hypervisor. Its VLANs, DHCP, DNS overrides, aliases, rules and BGP are applied by `ansible/playbooks/opnsense.yaml` through the OPNsense API. The playbook reads the network files plus `host_vars/opnsense.yaml`, and runs by hand from the laptop or Semaphore over the tailnet.

## Considered Options

- **VM on Proxmox** (the archive): snapshots and easy rebuilds, but every Proxmox update or host failure takes the internet down with it.
- **Two-node CARP**: real failover, but it needs a second NIC-rich box and three addresses per Network. Too much for a homelab.
- **Terraform provider** (`browningluke/opnsense`): real state and plans, but it's pre-1.0 and its README advises against production use. Also, Terraform Cloud's remote runs can't reach a LAN-only API without a self-hosted agent at home.
- **Hand configuration only**: nothing to maintain, but nothing reproducible after a reinstall.

## Consequences

- Each `oxlorg.opnsense` release supports only its matching OPNsense version. The collection is pinned in `requirements.yml`, and Renovate never automerges it; it's bumped together with the firmware.
- The collection has no modules for interface assignment or the Tailscale plugin, so those stay manual runbook steps. Rules match by description, and deleting them relies on the purge modules, which are still marked unstable.
- Recovery is: reinstall, restore `config.xml`, run the playbook. gl-router-home stays upstream as a fallback internet path, and jetkvm on its Network stays reachable over the tailnet when OPNsense is down.
