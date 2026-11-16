---
covers:
  - ansible/group_vars/all/network.yaml
  - ansible/group_vars/all/devices.yaml
---

# pve-nas

The steps done by hand on pve-nas: installing Proxmox VE on the SSD and bringing the existing data disks back without touching their contents. Everything after that comes from an Ansible playbook (see [Hand-over](#hand-over)). Addresses and Ports are in `ansible/group_vars/all/{network,devices}.yaml`, and [network.md](../network.md) lists them.

## Never touch a data disk

The two ZFS pools (`hdd0`, `hdd1`) and the NVMe XFS filesystem hold the data. This runbook only imports and mounts them. **Never** format, wipe, repartition or run `zpool create` on any disk except the 256 GB SATA SSD, and pick that SSD by size and model in the installer, never by its position in a list: the names `sda`, `sdb`, ... can change between boots.

If any step shows a pool or filesystem missing, stop and ask. Don't "fix" it by creating a new one.

## Console

The only way in until Proxmox is up is the console: kvm-switch input 3 (pve-nas HDMI and USB), reached through jetkvm, which sits on main behind gl-router-home's tailnet route. Select input 3 on the kvm-switch first.

## 1. Save a read-only listing

Before anything writes, boot a live USB (the Proxmox installer's debug shell, or any Linux live image) and save what the disks look like now:

```sh
zpool import        # lists importable pools; does not import them
lsblk -f
blkid
```

Copy the output to somewhere off the box (paste it into a file on your laptop through jetkvm, or `scp` it). Step 4 compares against it. Write down the NVMe filesystem's UUID from `blkid`: step 3 needs it.

`zpool import` with no arguments only reads. Don't add a pool name here.

## 2. Install Proxmox VE

1. Write the Proxmox VE installer ISO from proxmox.com to a USB stick and plug it into pve-nas.
2. Boot from it and run the graphical installer.
3. **Target disk**: the 256 GB SATA SSD only. Open *Options* and check the disk is the SSD by size and model. Leave every other disk unselected.
4. Network, on port 0 (the 1G port that runs to unifi-switch through patch-panel:9):
   - Address: `10.11.20.11/24`, the `servers` address of pve-nas in `network.yaml`.
   - Gateway: `10.11.20.1` (opnsense), the default route.
   - Hostname: `pve-nas`, with the domain the other Hosts use.
5. Set the root password and email when it asks, then install, remove the stick and reboot.
6. Check that it boots from the SSD and answers SSH on `10.11.20.11`. From here, work over SSH instead of the console.

Leave the storage NIC (port 1, `10.99.0.11`) unconfigured: the playbook sets it.

## 3. Import the pools and mount the NVMe

```sh
zpool import                  # both pools must be listed, as in step 1
zpool import -f hdd0          # -f: the pools were last used by another system
zpool import -f hdd1
zfs set mountpoint=/data/hdd0 hdd0
zfs set mountpoint=/data/hdd1 hdd1
```

`zfs set` only changes where the pool mounts. It writes no data.

Mount the NVMe XFS filesystem by UUID, from step 1's `blkid` listing:

```sh
mkdir -p /data/nvme
echo 'UUID=<nvme-uuid>  /data/nvme  xfs  defaults  0  2' >> /etc/fstab
systemctl daemon-reload
mount /data/nvme
```

Use the UUID from your listing. Never use `mkfs`, and don't mount by device name.

## 4. Check the result

Compare against the listing from step 1:

```sh
zpool status                  # hdd0 and hdd1 ONLINE, no errors
zfs list                      # the datasets from the listing are there, mounted under /data/hdd0 and /data/hdd1
findmnt /data/nvme            # xfs, same UUID as the listing
df -h /data/hdd0 /data/hdd1 /data/nvme
lsblk -f                      # every data disk and partition still matches the listing
```

Look at a few files in each mount to see the data is there. Then reboot and run the checks again: the pools and the fstab mount must come back by themselves.

## Hand-over

The runbook ends here. The pve-nas Ansible playbook (a separate task) takes over: the storage NIC, packages, users, SSH settings, NFS exports and the cluster. Don't set those by hand.
