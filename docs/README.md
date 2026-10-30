# Docs

What runs where, and how to change it. Docs describe the current state. One exception: `network.md`, `devices.md` and `diagrams/` describe the home network after the OPNsense cut-over, until it lands.

| Page | Covers |
|---|---|
| [overview.md](overview.md) | Start here: the parts, a Version Bump end to end, what each change triggers, who holds which credential |
| [architecture.md](architecture.md) | Network, DNS and TLS, secrets, data, backups, monitoring |
| [hosts.md](hosts.md) | Hosts and their assigned Services (generated) |
| [network.md](network.md) | Home Networks, addresses, Pools, SSIDs, tailnet routes and switch Ports; target state (generated) |
| [devices.md](devices.md) | Home Devices in rack order, their Ports and Cables, with the rack and KVM diagrams; target state (generated) |
| [services/](services/README.md) | Service catalog (generated), plus optional per-Service notes |
| [terraform.md](terraform.md) | Terraform Cloud setup, applying, adding a stack |
| [terraform-stacks.md](terraform-stacks.md) | Stacks and where they run (generated) |
| [automation.md](automation.md) | Renovate, PR checks, Auto-deploy via Semaphore |
| [runbooks/deploy.md](runbooks/deploy.md) | Deploying Services by hand |
| [runbooks/restore-backup.md](runbooks/restore-backup.md) | Restoring Service data from restic |
| [runbooks/rebuild-vps.md](runbooks/rebuild-vps.md) | Rebuilding the VPS from scratch |
| [runbooks/opnsense.md](runbooks/opnsense.md) | Installing OPNsense, its manual steps, restoring and upgrading it |
| [runbooks/manual-setup.md](runbooks/manual-setup.md) | One-time setup outside the repo: consoles, credentials, their order |

## Keeping docs current

Two git hooks keep the docs current. Install them once per clone with `just setup`.

- **Generated pages** (`hosts.md`, `services/README.md`, `terraform-stacks.md`, `network.md`, `devices.md` and the `.d2` diagrams in `diagrams/`) are written by `just docs` from the inventory, the Service definitions, `ansible/group_vars/all/{devices,network}.yaml` and the Terraform stacks. Never edit them by hand. `just docs` first validates the network files (unknown Ports, reused Ports, addresses outside their Network or inside the DHCP range, ...) and fails on any problem. It then renders each `.d2` to SVG with d2. The `docs-generate` hook regenerates them; if anything changed it aborts the commit so you can review and re-stage. The PR check fails if they're out of date. It compares the `.d2` sources but not the SVGs, whose bytes change with every d2 Version Bump.
- **Hand-written pages**, `CLAUDE.md` and the skills in `.claude/skills/` declare the code they describe in `covers:` frontmatter. The `docs-covers` hook refuses a commit that changes covered code without also staging every doc that covers it. If no doc needs a change, add a trailer to the commit message: `Docs: none (<reason>)`.
- Docs never mention versions. Renovate changes those, and its commits never run these hooks.

When adding a page, give it `covers:` globs that are as narrow as possible, and add it to the table above.
