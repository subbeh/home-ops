# The UniFi controller runs on the VPS, reached over the tailnet

The UniFi Network Application is a Service assigned to the VPS, not to a home Host. The home Hosts aren't set up yet, and the switch has to be adopted before the trunk works, so a controller at home would put a pve-nuc install on the critical path of the OPNsense bring-up. UniFi gear adopts over layer 3: a device on mgmt resolves `unifi.home.sbbh.cloud` (an Unbound override to the VPS's tailnet address), and OPNsense masquerades that traffic out of its tailscale interface. The VPS therefore only sees OPNsense's tailnet address, which the existing member grant already allows.

## Considered Options

- **Debian VM on pve-nuc** (the original plan): the controller is local and works without the tailnet, but it needs Proxmox and a VM up first.
- **pve-nuc as plain Debian**: fewer layers, but still blocks the bring-up on a home Host.

## Consequences

- Managing the home network depends on the VPS, the tailnet and OPNsense's NAT. Forwarding doesn't: UniFi devices keep their config when the controller is down.
- The VPS has about 2 GB of memory to spare and no swap, so the controller and its MongoDB get container memory limits. Running out of memory takes down management, not the network.
- Moving the controller later means a backup restore, then re-pointing `unifi.home.sbbh.cloud`, or re-adopting every device.
