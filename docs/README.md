# Docs

What runs where, and how to change it. Terms (Host, Service, Deploy, Version Bump, ...) are defined in [CONTEXT.md](../CONTEXT.md). Docs describe the current state; `.specs/` holds the design history behind it, and where the two disagree, these docs win.

| Page | Covers |
|---|---|
| [architecture.md](architecture.md) | Network, DNS and TLS, secrets, data, backups, monitoring |
| [hosts.md](hosts.md) | Hosts and their assigned Services (generated) |
| [services/](services/README.md) | Service catalog (generated), plus optional per-Service notes |
| [terraform.md](terraform.md) | Terraform Cloud setup, applying, adding a stack |
| [terraform-stacks.md](terraform-stacks.md) | Stacks and where they run (generated) |
| [automation.md](automation.md) | Renovate, PR checks, Auto-deploy via Semaphore |
| [runbooks/deploy.md](runbooks/deploy.md) | Deploying Services by hand |
| [runbooks/restore-backup.md](runbooks/restore-backup.md) | Restoring Service data from restic |
| [runbooks/rebuild-vps.md](runbooks/rebuild-vps.md) | Rebuilding the VPS from scratch |
| [runbooks/manual-setup.md](runbooks/manual-setup.md) | One-time setup outside the repo: consoles, credentials, their order |
| [adr/](adr/) | Architecture decisions |

## Keeping docs current

Two git hooks keep the docs current. Install them once per clone with `just setup`.

- **Generated pages** (`hosts.md`, `services/README.md`, `terraform-stacks.md`) are written by `just docs` from the inventory, the Service definitions and the Terraform stacks. Never edit them by hand. The `docs-generate` hook regenerates them; if anything changed it aborts the commit so you can review and re-stage. The PR check fails if they're out of date.
- **Hand-written pages**, `CLAUDE.md` and the skills in `.claude/skills/` declare the code they describe in `covers:` frontmatter. The `docs-covers` hook refuses a commit that changes covered code without also staging every doc that covers it. If no doc needs a change, add a trailer to the commit message: `Docs: none (<reason>)`.
- Docs never mention versions. Renovate changes those, and its commits never run these hooks.

When adding a page, give it `covers:` globs that are as narrow as possible, and add it to the table above.
