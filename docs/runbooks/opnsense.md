---
covers:
  - ansible/playbooks/opnsense.yaml
  - ansible/host_vars/opnsense.yaml
---
# OPNsense

The steps on the Topton that the API can't do, and how to restore and upgrade it. Everything else comes from `ansible/playbooks/opnsense.yaml` (ADR 0003). Networks, addresses and Ports are in `ansible/group_vars/all/{network,devices}.yaml`, and [network.md](../network.md) lists them.

Draft. Facts that aren't in this repo are marked TODO.

## Console

Until os-tailscale is up, the only way in is jetkvm, on kvm-switch input 1. jetkvm sits on main, reached over gl-router-home's tailnet route.

## 1. Install

1. Write the amd64 VGA installer image from opnsense.org to a USB stick, and plug it into the Topton.
2. Boot from it, log in as `installer` / `opnsense`, and install with ZFS onto the NVMe. Set the root password when the installer asks.
   > TODO(you): where the root password is kept.
3. Remove the stick and reboot.

## 2. Interfaces

At the console menu:

1. **Assign interfaces** (option 1). No VLANs here: the playbook creates them on the trunk.

   | OPNsense | Port | Network |
   |---|---|---|
   | WAN | opnsense:0 | main |
   | LAN | opnsense:1 | mgmt (native; the parent of the tagged VLANs) |
   | OPT1 | opnsense:3 | break-glass |

   > TODO(you): the NIC names (probably `igc0`-`igc3`). Match them by MAC, and record each MAC on its Port in `devices.yaml`.

2. **Set interface IP address** (option 2), IPv4 only. Say no to IPv6 everywhere.
   - WAN: static `192.168.11.10/24`, upstream gateway `192.168.11.1` (gl-router-home).
   - LAN: `10.11.10.1/24`, with the DHCP server on for `.100`-`.199`.
   - OPT1: `10.11.254.1/24`, with the DHCP server on for `.100`-`.199`.

   This DHCP server is only for the bootstrap. Kea takes over once the playbook runs.

3. OPT interfaces block everything by default, so break-glass can't reach the UI yet. Plug a laptop into opnsense:1, where LAN's anti-lockout rule allows it, and at `https://10.11.10.1`:
   - Firewall → Rules → OPT1: pass from `OPT1 net` to `This Firewall`, ports 443 and 22.
   - Interfaces → OPT1: rename it to `break-glass`.

## 3. Admin user

System → Access → Users → Add: a named user in group `admins`. Keep `root` for the console.

> TODO(you): the username, and where its password is kept.

## 4. API key

1. On that user, API keys → Add. The browser downloads `apikey.txt` with `key=` and `secret=`.
2. Store them in Secrets Manager as `OPNSENSE_API_KEY` and `OPNSENSE_API_SECRET`, the way [manual-setup.md](manual-setup.md#bitwarden) describes: a vault item field each, a key in `.bws.yaml`, then the sync.
3. Delete `apikey.txt`.

## 5. Tailscale

1. System → Firmware → Plugins: install `os-tailscale`.
2. VPN → Tailscale → Settings: enable it, log in, and advertise the route `10.11.0.0/16` plus an exit node, as `tailnet_routes.opnsense` in `network.yaml` says. The tailnet policy approves the routes (HO-3FW9).
   > TODO(you): auth key or interactive login, tags, key expiry.
3. Interfaces → Assignments: assign `tailscale0`, enable it, and name it `tailscale`.
4. Firewall → NAT → Outbound: switch to hybrid mode and add a rule on `tailscale`, source `LAN net` (mgmt), translation `Interface address`. UniFi gear then adopts through the VPS, which only sees OPNsense's tailnet address ([ADR 0006](../adr/0006-unifi-controller-on-the-vps.md)).
5. Firewall → Rules → tailscale: pass from any to `This Firewall`, ports 443 and 22. The tailnet policy decides who gets that far. The WAN gets no pass rules, so the UI and API stay closed there.

## 6. Check

From the laptop on the tailnet, with the key and secret from Secrets Manager:

```sh
curl -sk -u "$OPNSENSE_API_KEY:$OPNSENSE_API_SECRET" https://<opnsense tailnet name>/api/core/firmware/status
```

`-k` is needed until the ACME wildcard cert replaces the self-signed one. A laptop on break-glass gets a `10.11.254.x` lease and reaches `https://10.11.254.1`.

## Restore

1. Reinstall as in steps 1 and 2.
2. From break-glass, System → Configuration → Backups: restore `config.xml` from the backup repo. It brings back the users, the API key and every rule, but not the plugin packages.
   > TODO(you): the backup repo, once os-git-backup is set up (HO-QBVY).
3. Install `os-tailscale` by hand (step 5.1). The playbook reaches OPNsense over the tailnet, and it installs the other plugins.
4. Run the playbook, `--check --diff` first.

## Upgrade

`oxlorg.opnsense` must match the firmware, so they move together, and Renovate never automerges the collection.

1. System → Firmware → Updates: update, and reboot if it asks.
2. Bump `oxlorg.opnsense` in `requirements.yml` to the release that matches the new firmware.
3. Run the playbook with `--check --diff`. It should report no changes.
