# pve-nuc

The steps done by hand on pve-nuc: installing Proxmox VE on its NVMe. Everything after that comes from `ansible/playbooks/pve.yaml` (see [Hand-over](#hand-over)). Addresses and Ports are in `ansible/group_vars/all/{network,devices}.yaml`, and [network.md](../network.md) lists them.

pve-nuc holds no data to keep: the install wipes the 1 TB NVMe, its only disk.

## Console

The only way in until Proxmox is up is the console: kvm-switch input 2 (pve-nuc HDMI and USB), reached through jetkvm, which sits on main behind gl-router-home's tailnet route. Select input 2 on the kvm-switch first.

## 1. Install Proxmox VE

1. Write the Proxmox VE installer ISO from proxmox.com to a USB stick and plug it into pve-nuc.
2. Boot from it and run the graphical installer.
3. **Target disk**: the 1 TB NVMe, ext4.
4. Network, on its one Port (`eth`, to unifi-switch:11 through patch-panel:8). Check that unifi-switch:11 is native servers with nothing tagged in UniFi, as in `devices.yaml`, then overwrite the installer's DHCP lease:
   - Address: `10.11.20.10/24`, the `servers` address of pve-nuc in `network.yaml`.
   - Gateway: `10.11.20.1` (opnsense), the default route.
   - Hostname: `pve-nuc`, with the domain the other Hosts use.
5. Set the root password and email when it asks, then install, remove the stick and reboot.
6. Check that it boots from the NVMe and answers SSH on `10.11.20.10` and the web UI on `https://10.11.20.10:8006`. From here, work over SSH instead of the console.
7. Append the home-ops public key (`pve_root_authorized_key` in `ansible/group_vars/pve.yaml`) to `/root/.ssh/authorized_keys`, so the playbook can connect. The playbook keeps it there and turns password logins off.
8. Note the Port's MAC from `ip -br link` for `devices.yaml`.

## Hand-over

The runbook ends here. `ansible/playbooks/pve.yaml` takes over: packages, Cockpit, SSH settings and the API user. It also creates nuc-svc, the Docker LXC (`pve_lxc` in `ansible/host_vars/pve-nuc.yaml`). pve-nuc has no storage address or NFS exports, so the playbook skips those. Don't set any of it by hand.

Then join the cluster by hand, from pve-nas's runbook: [Form the cluster](pve-nas.md#5-form-the-cluster).
