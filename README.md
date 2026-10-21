# home-ops

Infrastructure for my personal Hosts and the self-hosted Services that run on them: Ansible deploys Docker containers, Terraform Cloud manages DNS and the tailnet policy, and Renovate keeps versions current, with Version Bumps Auto-deployed through Semaphore.

> [!NOTE]
> The previous version (a Talos/Flux Kubernetes cluster) lives in the [`archive`](../../tree/archive) branch.

## Layout

| Path | What |
|---|---|
| `ansible/services/` | One file per Service: files, containers, secrets |
| `ansible/roles/services/` | The role that deploys them |
| `ansible/inventory.yml` | Hosts and their Assignments |
| `terraform/` | Terraform stacks: Cloudflare DNS, the Tailscale policy, TFC workspaces |
| `.github/workflows/` | PR checks and Auto-deploy |
| `.renovate/` | Renovate presets |
| `docs/` | How it all works: [overview](docs/overview.md), [index](docs/README.md) |

## Getting started

```sh
mise install     # tools, pinned in .mise/config.toml
just setup       # git hooks that keep docs/ current, Ansible collections
just --list      # everything else
```

`BWS_ACCESS_TOKEN` (Bitwarden Secrets Manager) goes in `.env`, which mise loads.
