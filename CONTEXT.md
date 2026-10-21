# home-ops

Infrastructure for personal hosts and the self-hosted services that run on them.

## Language

**Host**:
A machine managed by this repo.
_Avoid_: server, node, box

**Device**:
A physical piece of equipment on the home network, such as a server, switch, router, KVM or PDU.
_Avoid_: node, box, hardware

**Port**:
A physical socket on a Device: ethernet (1G or 2.5G), HDMI or USB.

**Cable**:
A physical connection between exactly two Ports.
_Avoid_: link, connection

**Network**:
One IP subnet on one layer-2 segment, optionally VLAN-tagged. The tailnet is also a Network.
_Avoid_: VLAN (a Network may have one), subnet, LAN

**Pool**:
An address range that Hosts announce to the router over BGP, not tied to any layer-2 segment (e.g. Kubernetes LoadBalancer addresses).
_Avoid_: Network (a Pool has no segment), range

**Service**:
A named, self-contained unit of self-hosted software (one or more containers plus their files and tasks) that can be deployed to a Host.
_Avoid_: app, stack

**Assignment**:
The explicit statement that a Service runs on a specific Host. Services are only ever assigned to individual Hosts, never to groups.

**Step**:
One phase of deploying a Service: pre-tasks, files, containers, post-tasks.

**Deploy**:
Running the services playbook for one or more Services on the Hosts they are assigned to.
_Avoid_: rollout, release

**Version Bump**:
A change that only moves a Service's pinned image version, proposed by Renovate.
_Avoid_: upgrade, update (ambiguous with config edits)

**Auto-deploy**:
A Deploy triggered without a human, which happens only when a Version Bump is merged.

## Relationships

- A bare-metal **Host** is also a **Device**; the VPS and VMs are **Hosts** but not **Devices**, and a switch is a **Device** but not a **Host**
- A **Device** has **Ports**; a **Cable** joins two **Ports**, so a run through a patch panel is two **Cables**, paired by the panel's front and back **Ports**
- A **Device** may have an address on one or more **Networks** without being a **Host** (e.g. the KVM)
- A **Host** has zero or more **Assignments**; each **Assignment** names exactly one **Service**
- A **Service** may be assigned to more than one **Host**; a **Deploy** of such a Service must target a single Host
- A **Version Bump** touches one or more **Services** (e.g. a shared image); its **Auto-deploy** covers exactly those Services
- Semaphore is a **Service** that is never **Auto-deployed**

## Flagged ambiguities

- "upgraded service" was used for both Version Bumps and hand-made config changes. Resolved: only **Version Bumps** trigger an **Auto-deploy**; hand edits are deployed manually.
