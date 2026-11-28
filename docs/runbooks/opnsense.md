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

1. **Assign interfaces** (option 1). No VLANs here: the playbook creates and assigns them on the trunk, and sets their addresses.

   | OPNsense | Port       | Network                                       |
   | -------- | ---------- | --------------------------------------------- |
   | WAN      | opnsense:0 | main                                          |
   | LAN      | opnsense:1 | mgmt (native; the parent of the tagged VLANs) |
   | OPT1     | opnsense:3 | backdoor                                   |

2. **Set interface IP address** (option 2), IPv4 only. Say no to IPv6 everywhere.
   - WAN: static `192.168.11.10/24`, upstream gateway `192.168.11.1` (gl-router-home).
   - LAN: `10.11.10.1/24`, with the DHCP server on for `.100`-`.199`.
   - OPT1: `10.11.254.1/24`, with the DHCP server on for `.100`-`.199`.

   This DHCP server (dnsmasq) is only for the bootstrap. The playbook turns dnsmasq off and hands DHCP to Kea, and it also turns IPv6 off on LAN and OPT1 if the console left it on.

3. OPT interfaces block everything by default, so backdoor can't reach the UI yet. Reach it through a reverse tunnel instead: at the console, open the shell (option 8) and forward your laptop's port 4443 to the UI. The WAN allows outbound traffic, so the laptop only has to be reachable from main.

   ```sh
   ssh -R 4443:localhost:443 <you>@<laptop>
   ```

   Then, at `https://localhost:4443` on the laptop:
   1. Firewall → Aliases → Add: name `backdoor_ports`, type Port(s), content `22`, `443` and `8443`. Save, then Apply. The UI is on `443` until step 5.8 moves it to `8443`, and the playbook then drops `443`.
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

   The playbook adopts the alias by its name and the rule by its description, so keep both spelled as here.

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
   - Tick Advertise Exit Node, and under Subnets advertise `10.11.0.0/16`, as `tailnet_routes.opnsense` in `network.yaml` says. The playbook also gives clients the same prefix over DHCP (option 121) through the LAN gateway, so laptops that accept routes can use the LAN at home instead of the tunnel.
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

   Then add a second rule the same way, with Source `SERVERS net` and Description `servers to the tailnet, for backup heartbeats`.

   The rest of Translation keeps its defaults. The interface address rewrites the source of mgmt and servers traffic to OPNsense's own tailnet address, and maps the replies back. Automatic NAT only covers interfaces with a gateway, which leaves tailscale out. UniFi gear adopts through the VPS, and nas-svc and nuc-svc push their backup heartbeats to Gatus on it; the VPS only sees OPNsense's tailnet address, which the tailnet policy lets in as a member device.
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
   | Description            | `Tailnet: UI and SSH`   |

   Source is any because the tailnet policy already decides which nodes get this far. This rule only opens OPNsense itself. Tailnet traffic to the Networks behind it, and through the exit node, stays blocked until the playbook's rules land. The playbook adopts this rule by its description. It deletes a `tailnet: UI and SSH` rule, since a floating one by that name once opened the UI on every interface. The mgmt and servers NAT from step 5.6 needs no rule here, because replies match its state. The WAN gets no pass rules, so the UI and API stay closed there.
8. System → Settings → Administration → Web GUI: add `opnsense.sbbh.cloud` to Alternate Hostnames, set TCP port to `8443`, then Save. The UI rejects any hostname it doesn't know as a possible DNS rebind attack. That name is the Cloudflare record for the tailnet address, in `terraform/cloudflare/records.auto.tfvars`. Keep the DNS rebind check itself on. Port `443` is left to the [home ingress](#home-ingress), and the playbook calls the API on `8443`. The page reloads at the new port.

## 6. Check

From the laptop on the tailnet, with the key and secret from Secrets Manager:

```sh
curl -sk -u "$OPNSENSE_API_KEY:$OPNSENSE_API_SECRET" https://<opnsense tailnet name>:8443/api/core/firmware/status
```

`-k` is needed until step 7 points the UI at the ACME cert. After that, drop it and use `https://opnsense.sbbh.cloud:8443`. A laptop on backdoor gets a `10.11.254.x` lease and reaches `https://10.11.254.1:8443`.

## 7. UI certificate

The playbook issues the `opnsense.sbbh.cloud` cert through the ACME client, but the UI's certificate setting has no API. After the first playbook run:

1. Services → ACME Client → Certificates: check `opnsense.sbbh.cloud` shows a successful issue.
2. System → Settings → Administration → Web GUI → SSL Certificate: pick `opnsense.sbbh.cloud`, then Save. Renewals keep the same entry, and the playbook's restart action reloads the UI.
3. `curl https://opnsense.sbbh.cloud:8443/api/core/firmware/status` (with the API key) works without `-k`.

## 8. Config backup

os-git-backup commits `config.xml` to a private GitHub repo after every config change. The file holds password hashes, API keys and the Cloudflare token, so the repo stays private. The playbook installs the plugin, but `oxlorg.opnsense` has no module for its settings, so the rest is by hand.

1. Create the private repo `opnsense-config`, empty.
2. On the laptop, make a key pair for it: `ssh-keygen -t ed25519 -N '' -C opnsense-git-backup -f ~/opnsense-backup`.
3. Add `~/opnsense-backup.pub` as a deploy key with write access: `gh repo deploy-key add ~/opnsense-backup.pub --repo <owner>/opnsense-config --allow-write --title opnsense`. Save in the next step tests the connection, so the key must be there first.
4. System → Configuration → Backups → Git: tick Enable, set the URL to `ssh://github.com/<owner>/opnsense-config.git` (it refuses a user in the URL), the Username to `git`, the Branch to `main` and the SSH private key to the contents of `~/opnsense-backup`. Leave Password empty and force push off. Save, then check that the repo gets a commit. Each later config change adds one.
5. `rm ~/opnsense-backup ~/opnsense-backup.pub`: the private key now lives in `config.xml`.

After a reinstall, the firewall's git history starts empty, so its first push to `main` is refused. Point the backup at a new branch rather than turning force push on, which would overwrite the old history.

## Rules and aliases

The playbook makes an alias for each Network, Pool and address name in `network.yaml`, plus `home` (all of them), and the pass rules in `host_vars/opnsense.yaml`. Everything else is blocked by default. It matches aliases by name and rules by description, and it never deletes what's dropped from those lists, because the collection's purge modules are unstable. To remove a rule, delete it under Firewall → Rules, or add its description to the playbook's removal task. Renaming a rule leaves the old one behind as well.

There's no rollback: OPNsense dropped the filter savepoint API. If a rule change cuts the tailnet, a laptop on opnsense:1 still reaches `https://10.11.10.1:8443` through LAN's anti-lockout rule.

## Home ingress

HAProxy (os-haproxy) serves every home Service at `https://<service>.svc.sbbh.cloud` (`ingress_domain` in `group_vars/all/services.yaml`). The playbook builds it all from the inventory: every Service with an `ingress: {port: N}` key on a `local` Host gets a server, a backend and a line in one map file, plus a line per name in its `aliases`. The frontend listens on OPNsense's servers address `:443` only, so the WAN never sees it, and clients and the tailnet reach it through their pass rules. One Unbound override answers `*.svc.sbbh.cloud` with that address, and there's no public record. The `*.svc.sbbh.cloud` cert comes from the ACME client, like the UI's, and a renewal restarts HAProxy.

- **A new or moved Service**: Deploy it, run this playbook, and Deploy `gatus`, which checks every route over the tailnet.
- **Dropped Services**: the map is rewritten, so the name stops routing on the next run, but the server and backend stay until deleted under Services → HAProxy.
- **Private Services** (`ansible/services/<name>.private.yaml`, gitignored) exist only in the main checkout. The playbook refuses to run from a checkout that lacks one, since it would drop the route.
- **Direct access**: a Service's published port also answers plain HTTP to clients and the tailnet, since their pass rules allow every Network. Blocking it needs a block rule ahead of those rules, which means giving every rule a sequence.
- **Websockets**: HAProxy's defaults carry `timeout tunnel 1h`, so an idle upgraded connection stays open for an hour instead of being cut at the 30s client and server timeouts.
- **`--check`**: before os-haproxy is installed, the check skips HAProxy. Before its objects exist, the steps that link to them fail and are ignored.

Moving the UI off `443` on a box that predates this: add `8443` to the `backdoor_ports` alias and Apply, set step 5.8's TCP port, then run the playbook, which drops `443` from the alias.

## iperf3

os-iperf runs an iperf3 server on `5201`, so any Host can measure throughput to OPNsense. The plugin can't bind an address, so it listens on every interface; the WAN stays closed because it has no pass rules. clients and the tailnet reach it through their every-Network rules, and servers through its own rule. Each playbook run starts the server job when none is listening. A reboot stops it until the next run; start it by hand under Interfaces → Diagnostics → Iperf Server in the meantime. Before os-iperf is installed, `--check` skips it.

## Restore

1. Reinstall as in steps 1 and 2.
2. From backdoor, System → Configuration → Backups: restore `config.xml` from the backup repo. It brings back the users, the API key and every rule, but not the plugin packages.
   The repo is the private `opnsense-config` on GitHub (step 8). Pull `config.xml` from it with the deploy key's clone URL, or copy it from a laptop checkout, then upload it in that page.
3. Install `os-tailscale` by hand (step 5.1). The playbook reaches OPNsense over the tailnet, and it installs the other plugins.
4. Run the playbook from main on the laptop, with `just ansible::playbook opnsense --check --diff` first.

## Upgrade

The playbook installs minor firmware updates itself. A major upgrade goes through the UI, because `oxlorg.opnsense` must match the firmware, so they move together, and Renovate never automerges the collection.

1. System → Firmware → Updates: upgrade, and reboot if it asks.
2. Bump `oxlorg.opnsense` in `requirements.yml` to the release that matches the new firmware, then `ansible-galaxy collection install -r requirements.yml`.
3. Run the playbook with `--check --diff`. It should report no changes.
