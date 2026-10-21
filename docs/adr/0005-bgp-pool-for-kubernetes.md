# Kubernetes LoadBalancer addresses are a Pool announced over BGP to OPNsense

LoadBalancer addresses come from the Pool `k8s-lb` (`10.11.80.0/24`). The k8s Hosts announce it over BGP to OPNsense (`os-frr`, AS 64508 → 64500), rather than through L2 announcements inside the servers Network. This gives ECMP across nodes, faster failover, and an address range the firewall can target as one alias, separate from the Hosts' own addresses. It's why "Pool" exists in the glossary: the range is routed, not on any layer-2 segment, so it isn't a Network.

## Considered Options

- **L2 announcements (Cilium/MetalLB) in a reserved range of servers**: no FRR on OPNsense, no ASNs, fewer moving parts. On an N5105, one fewer plugin also means one fewer upgrade risk.

## Consequences

- OPNsense runs the FRR plugin, and its neighbours are generated from the Pool's `announced_by`. The cluster side (Talos/Cilium BGP config) must stay in step with `network.yaml`.
