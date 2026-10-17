# Auto-deploy via Semaphore on the VPS, triggered from GitHub Actions over Tailscale

Merged Renovate Version Bumps are deployed by a GitHub Actions workflow that joins the tailnet as an ephemeral `tag:ci` node and starts a task on Semaphore (running as a Service on the VPS), scoped to the changed Services; the workflow waits on the task and mirrors its result. Only Version Bumps Auto-deploy: hand edits to Services, the role, group_vars or inventory are always deployed manually with `just`, because their blast radius is unpredictable and the role recreates every container it touches.

## Considered Options

- **GitHub Actions runs Ansible directly over SSH**: no extra Service, but CI would hold a root SSH key and the Bitwarden token for a public repo, and there'd be no run history outside the Actions tab.
- **Public Semaphore webhook**: avoids Tailscale in CI, but exposes Semaphore to the internet and leaves change detection to Semaphore.
- **Ascender (AWX)**: needs k3s + Postgres; far too heavy for one VPS.
- **Ansible Automation Platform (developer subscription)**: RHEL-only containerized installer, ~16-20 GB RAM / 4 vCPU; the VPS is Ubuntu with 4 GB. Shelved until there's a dedicated RHEL host.
- **Self-hosted GitHub runner on the VPS**: no inbound access needed, but a self-hosted runner on a public repo is a standing risk.
- **ansible-pull on a timer**: no extra Service, but no UI, and the "only Version Bumps, only changed Services" logic would move onto the VPS.

## Consequences

- Semaphore cannot Auto-deploy itself (recreating its container kills the running task); its Version Bumps never automerge and are deployed manually.
- The CI node's reach is limited by the tailnet policy, which is therefore managed in Terraform (`terraform/tailscale`) as a whole file.
- A Service assigned to more than one Host makes the Auto-deploy fail until the workflow learns to run per Host.
