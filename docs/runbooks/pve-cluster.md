# pve cluster

The steps done by hand to join pve-nas and pve-nuc into the Proxmox cluster `home-ops`. Addresses are in `ansible/group_vars/all/network.yaml`, and [network.md](../network.md) lists them.

## Form the cluster

Once both run Proxmox ([pve-nas.md](pve-nas.md), [pve-nuc.md](pve-nuc.md)), pve-nas and pve-nuc form one cluster, once, by hand: the pve playbook doesn't create, join or check it. corosync runs over servers, since pve-nuc has no storage Port. pve-nas gets 2 votes and pve-nuc 1, so pve-nas stays quorate on its own and a pve-nuc outage costs nothing.

pve-nuc must hold no guests, since joining replaces its `/etc/pve` with the cluster's: join before the pve playbook creates nuc-svc on it. Its Proxmox users go too, but pve-nas has the same API user. vmids are cluster-wide, so each `pve_lxc` takes its own (`<vlan><host number>` keeps them apart).

On pve-nas:

```sh
pvecm create home-ops --link0 10.11.20.11
```

On pve-nuc:

```sh
pvecm add 10.11.20.11 --link0 10.11.20.10
```

The join goes through pve-nas's API: it asks for pve-nas's root password and to confirm its certificate fingerprint, so SSH password logins stay off.

Then on pve-nas, give it its second vote. `corosync.conf` is shared by both nodes and applies as soon as it changes, so edit a copy inside `/etc/pve` and move it into place:

```sh
cp /etc/pve/corosync.conf /root/corosync.conf.bak
cp /etc/pve/corosync.conf /etc/pve/corosync.conf.new
# in the copy: set quorum_votes: 2 in pve-nas's node block, and raise totem's config_version by 1
mv /etc/pve/corosync.conf.new /etc/pve/corosync.conf
```

Check on both nodes: `pvecm status` shows `Quorate: Yes`, `Expected votes: 3` and `Total votes: 3`, with pve-nas at 2 votes.

While pve-nas is down, pve-nuc's `/etc/pve` is read-only: its guests keep running, but none can be started or changed until `pvecm expected 1` on pve-nuc. A rebuilt pve-nuc rejoins the same way, after `pvecm delnode pve-nuc` on pve-nas.
