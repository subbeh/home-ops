# The network is described by plain YAML in group_vars, and everything else derives from it

Devices, Ports, Cables, Networks, Pools and every address live in `ansible/group_vars/all/devices.yaml` and `network.yaml`. Docs, D2 diagrams, OPNsense config, Gatus endpoints and the Terraform stacks all read them, so each fact is written once and changed through a reviewed PR. The files describe the post-OPNsense target until the cut-over lands, which is the one exception to "docs describe the current state".

## Considered Options

- **NetBox**: a proper DCIM/IPAM UI, cable tracing and an API. But the data model (sites, manufacturers, device types) needs heavy setup before anything useful can be entered. It's another stateful Service to run and back up, and every consumer would need an API call instead of a file read. It was tried once and abandoned over the setup cost.
- **draw.io as the source, with hand-written Markdown beside it**: the least effort, but not machine-readable, so the diagram and the text drift and nothing can be validated or consumed.
- **Addresses stay per tool** (inventory host vars, `cloudflare/main.tf`, `policy.hujson`): the status quo, where the VPS's IP was written in three places.

## Consequences

- The files hold no Jinja, because Terraform reads them with `yamldecode`. The cloudflare and tailscale workspaces need trigger patterns for `network.yaml`.
- The group var `networks:` replaces the inventory's per-Host `networks:` host var, which would otherwise shadow it.
- UniFi switch ports and SSIDs are documented but configured by hand, so drift between the file and the controller is caught only by review.
