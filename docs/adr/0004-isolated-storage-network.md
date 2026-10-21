# The storage Network is unrouted, and OPNsense is not attached to it

The 2.5G switch carries only the storage Network (`10.99.0.0/24`, outside `10.11.0.0/16`): no VLAN, no gateway, static addresses, and OPNsense port 2 stays unconnected even though the switch has a free port. The 2.5G Hosts (k8s-nuc, both Optiplexes, pve-nas) are dual-homed, with their default route via servers on the 1G UniFi switch. A routed storage Network would send replies out the other interface, so OPNsense would drop the asymmetric flows. Kept unrouted, storage traffic doesn't depend on the firewall (OPNsense reboots and upgrades don't touch NFS mounts), and the exports are reachable only from Hosts physically on the switch. Attaching OPNsense would add no throughput either: clients reach servers through the 1G trunk, and WAN sits behind gl-router-home.

## Considered Options

- **Route storage via OPNsense port 2**: reachable from other Networks and the tailnet, at the cost of policy routing on every dual-homed Host and routable NFS.
- **Make the 2.5G switch the servers Network**: one NIC per Host, but nuc-01 (1G only) has no port left, so servers would have to span both switches through a software bridge on OPNsense.

## Consequences

- Storage gets no DHCP, no DNS, no Gatus checks, and no tailnet route. nuc-01 reaches the NAS over servers at 1G.
- Revisit this if a managed 2.5G core switch replaces the UniFi Lite 16, since that's when a 2.5G trunk to OPNsense would start to pay off.
