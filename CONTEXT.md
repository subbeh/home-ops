# home-ops

Infrastructure for personal hosts and the self-hosted services that run on them.

## Language

**Host**:
A machine managed by this repo.
_Avoid_: server, node, box

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

- A **Host** has zero or more **Assignments**; each **Assignment** names exactly one **Service**
- A **Service** may be assigned to more than one **Host**; a **Deploy** of such a Service must target a single Host
- A **Version Bump** touches one or more **Services** (e.g. a shared image); its **Auto-deploy** covers exactly those Services
- Semaphore is a **Service** that is never **Auto-deployed**

## Flagged ambiguities

- "upgraded service" was used for both Version Bumps and hand-made config changes. Resolved: only **Version Bumps** trigger an **Auto-deploy**; hand edits are deployed manually.
