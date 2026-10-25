---
covers:
  - ansible/playbooks/opnsense.yaml
  - ansible/host_vars/opnsense.yaml
---

# OPNsense

The steps on the Topton that the API can't do, and how to restore and upgrade it. Everything else comes from `ansible/playbooks/opnsense.yaml` (ADR 0003). Networks, addresses and Ports are in `ansible/group_vars/all/{network,devices}.yaml`, and [network.md](../network.md) lists them.

Open questions are marked TODO.

## Console

Until os-tailscale is up, the only way in is jetkvm, on kvm-switch input 1. jetkvm sits on main, reached over gl-router-home's tailnet route.

## 1. Install

1. Write the amd64 DVD installer image from opnsense.org to a USB stick, and plug it into the Topton.
2. Boot from it, log in as `installer` / `opnsense`, and install with ZFS onto the NVMe. Set the root password when the installer asks.
3. Remove the stick and reboot.

## 2. Interfaces

At the console menu:

1. **Assign interfaces** (option 1). No VLANs here: the playbook creates them on the trunk.

   | OPNsense | Port       | Network                                       |
   | -------- | ---------- | --------------------------------------------- |
   | WAN      | opnsense:0 | main                                          |
   | LAN      | opnsense:1 | mgmt (native; the parent of the tagged VLANs) |
   | OPT1     | opnsense:3 | backdoor                                   |

2. **Set interface IP address** (option 2), IPv4 only. Say no to IPv6 everywhere.
   - WAN: static `192.168.11.10/24`, upstream gateway `192.168.11.1` (gl-router-home).
   - LAN: `10.11.10.1/24`, with the DHCP server on for `.100`-`.199`.
   - OPT1: `10.11.254.1/24`, with the DHCP server on for `.100`-`.199`.

   This DHCP server is only for the bootstrap. Kea takes over once the playbook runs.

3. OPT interfaces block everything by default, so backdoor can't reach the UI yet. Reach it through a reverse tunnel instead: at the console, open the shell (option 8) and forward your laptop's port 4443 to the UI. The WAN allows outbound traffic, so the laptop only has to be reachable from main.

   ```sh
   ssh -R 4443:localhost:443 <you>@<laptop>
   ```

   Then, at `https://localhost:4443` on the laptop:
   1. Firewall → Aliases → Add: name `backdoor_ports`, type Port(s), content `22` and `443`. Save, then Apply.
   2. Firewall → Rules → OPT1 → Add, then Save and Apply changes:

      | Field                  | Value                  |
      | ---------------------- | ---------------------- |
      | Action                 | Pass                   |
      | Direction              | in                     |
      | TCP/IP Version         | IPv4                   |
      | Protocol               | TCP                    |
      | Source                 | `OPT1 net`             |
      | Destination            | `This Firewall`        |
      | Destination port range | `backdoor_ports`       |
      | Description            | `backdoor: UI and SSH` |

   3. Interfaces → OPT1: set the description to `BACKDOOR` and tick Prevent interface removal. The rule refers to the interface as `opt1`, so the rename doesn't break it.

   The tunnel goes through localhost, so the rule takes no part in it. To test the rule, plug a laptop into opnsense:3: it gets a `10.11.254.x` lease, reaches `https://10.11.254.1` and SSH, and nothing else.

   Without the tunnel, a laptop on opnsense:1 works too, since LAN's anti-lockout rule lets it in at `https://10.11.10.1`.

   > TODO: check how these hand-made rules and the alias interact with the playbook's rules and aliases.

## 3. Admin user

Keep `root` for the console. Every other way in uses a named user.

1. System → Access → Users → Add: a named user in group `admins`, with:
   - Login shell: `/bin/sh`. The default, `/usr/sbin/nologin`, refuses SSH even with the right key.
   - Authorized keys: your SSH public key.
2. System → Settings → Administration → Secure Shell: tick Enable Secure Shell, and leave Permit root user login and Permit password login off. Save. From now on, SSH means a named user with a key.
3. Same page, Authentication → Sudo: Ask password, group `admins`, so the named user can run root commands.
4. TOTP for the UI:
   1. System → Access → Servers → Add: type `Local + Timebased One Time Password`, name `TOTP`, and tick Reverse token order so the password comes first. Keep the other defaults (6 digits, 30 s).
   2. On the user: tick Generate new secret, Save, and scan the QR code into the authenticator app. A seed alone changes nothing; step 4.3 turns it on.
   3. System → Settings → Administration → Authentication → Server: select `TOTP` only. If `Local Database` stays selected, the password alone still logs in.
   4. In a private window, log in with the password followed by the token in the password field (for example `hunter2123456`). There's no separate field.

   > TODO: does the TOTP server apply to SSH password logins and the API? Keys and API keys should bypass it.

## 4. API key

1. On that user, API keys → Add. The browser downloads `apikey.txt` with `key=` and `secret=`.
2. Store them in Secrets Manager as `OPNSENSE_API_KEY` and `OPNSENSE_API_SECRET`, the way [manual-setup.md](manual-setup.md#bitwarden) describes: a vault item field each, a key in `.bws.yaml`, then the sync.
3. Delete `apikey.txt`.

## 5. Tailscale

1. System → Firmware → Plugins: install `os-tailscale`.
2. In the Tailscale admin console, Settings → Keys → Generate auth key: not reusable, not ephemeral, no tags. The key only registers the node, so its own expiry doesn't matter once it's used. Leaving out tags makes the node yours, so the policy's `autogroup:member` rule already covers it.
3. VPN → Tailscale → Settings:
   - Tick Enabled, and paste the auth key into Pre-authentication Key.
   - Tick Advertise Exit Node, and under Subnets advertise `10.11.0.0/16`, as `tailnet_routes.opnsense` in `network.yaml` says.
   - Leave Accept Subnet Routes and Accept DNS off. gl-router-home advertises `192.168.11.0/24`, which is OPNsense's WAN, and accepting it would route the WAN into the tailnet.

   Save, then check that the node shows up in the admin console.
4. Admin console → Machines → opnsense:
   - ⋯ → Disable key expiry. Node keys otherwise expire after 180 days, and OPNsense would drop off the tailnet until someone logs it in again.
   - ⋯ → Edit route settings: approve `10.11.0.0/16` and the exit node. Approving by hand lasts until `autoApprovers` in `terraform/tailscale/policy.hujson` takes over.
5. Interfaces → Assignments: assign `tailscale0`, enable it, and name it `TAILSCALE`.
6. Firewall → NAT → Source NAT (Outbound on older firmware). If the page has a mode, pick Hybrid, so the automatic WAN rules stay. Then Add, Save and Apply:

   | Field               | Value                                       |
   | ------------------- | ------------------------------------------- |
   | Interface           | `TAILSCALE`                                 |
   | TCP/IP Version      | IPv4                                        |
   | Protocol            | any                                         |
   | Source              | `LAN net` (mgmt)                            |
   | Destination         | any                                         |
   | Translate Source IP | left empty (the default, interface address) |
   | Description         | `mgmt to the tailnet, for UniFi adoption`   |

   The rest of Translation keeps its defaults. The interface address rewrites the source of mgmt traffic to OPNsense's own tailnet address, and maps the replies back. Automatic NAT only covers interfaces with a gateway, which leaves tailscale out. UniFi gear adopts through the VPS, which only sees OPNsense's tailnet address ([ADR 0006](../adr/0006-unifi-controller-on-the-vps.md)).
7. Firewall → Rules → TAILSCALE → Add, then Save and Apply changes:

   | Field                  | Value                   |
   | ---------------------- | ----------------------- |
   | Action                 | Pass                    |
   | Direction              | in                      |
   | TCP/IP Version         | IPv4                    |
   | Protocol               | TCP                     |
   | Source                 | any                     |
   | Destination            | `This Firewall`         |
   | Destination port range | `backdoor_ports`        |
   | Description            | `tailnet: UI and SSH`   |

   Source is any because the tailnet policy already decides which nodes get this far. This rule only opens OPNsense itself. Tailnet traffic to the Networks behind it, and through the exit node, stays blocked until the playbook's rules land. The mgmt NAT from step 5.6 needs no rule here, because replies match its state. The WAN gets no pass rules, so the UI and API stay closed there.
8. System → Settings → Administration → Web GUI: add `opnsense.sbbh.cloud` to Alternate Hostnames, then Save. The UI rejects any hostname it doesn't know as a possible DNS rebind attack. That name is the Cloudflare record for the tailnet address, in `terraform/cloudflare/records.auto.tfvars`. Keep the DNS rebind check itself on.

## 6. Check

From the laptop on the tailnet, with the key and secret from Secrets Manager:

```sh
curl -sk -u "$OPNSENSE_API_KEY:$OPNSENSE_API_SECRET" https://<opnsense tailnet name>/api/core/firmware/status
```

`-k` is needed until the ACME wildcard cert replaces the self-signed one. A laptop on backdoor gets a `10.11.254.x` lease and reaches `https://10.11.254.1`.

## Restore

1. Reinstall as in steps 1 and 2.
2. From backdoor, System → Configuration → Backups: restore `config.xml` from the backup repo. It brings back the users, the API key and every rule, but not the plugin packages.
   > TODO(you): the backup repo, once os-git-backup is set up.
3. Install `os-tailscale` by hand (step 5.1). The playbook reaches OPNsense over the tailnet, and it installs the other plugins.
4. Run the playbook, `--check --diff` first.

## Upgrade

`oxlorg.opnsense` must match the firmware, so they move together, and Renovate never automerges the collection.

1. System → Firmware → Updates: update, and reboot if it asks.
2. Bump `oxlorg.opnsense` in `requirements.yml` to the release that matches the new firmware.
3. Run the playbook with `--check --diff`. It should report no changes.
