---
name: add-service
description: Add a new self-hosted Service (ansible/services/<name>.yaml) and assign it to a Host. Use when asked to add, host, self-host or set up an app or container.
covers:
  - ansible/roles/services/**
  - ansible/group_vars/all/services.yaml
  - ansible/services/traefik.yaml
---
# Add a Service

The schema is the services role (`ansible/roles/services/tasks/`). Existing Services in `ansible/services/` are working examples: karakeep has several containers and secrets, syncthing uses host networking, aven has a custom owner.

## Steps

1. **Gather** from the upstream self-hosting docs: the image with an exact tag, the port, the paths that need to persist, the env vars, and which of them are secrets. Ask the user for the Host and any hostname other than `<container name>.<services_domain>`. Done when every field of the template below has a value.
2. **Write** `ansible/services/<name>.yaml` from the template. Done when `just check` passes.
3. **Secrets**: name them `<SERVICE>_<PURPOSE>` (e.g. `KARAKEEP_NEXTAUTH_SECRET`) and list them for the user to add to `.bws.yaml` (the dotfiles bws sync creates them in Secrets Manager; don't read the file). The role fails a Deploy on any missing key.
4. **Assign**: append `<name>` to the Host's `services:` in `ansible/inventory.yml`.
5. **Docs**: run `just docs` and stage the generated pages. One-time manual setup (first-run commands, UI steps) goes in the Service file's header comment, as in aven and semaphore. A new Service file has no covering doc; the commit-msg hook checks the rest.
6. **Verify**: run `just check`. To Deploy, hand over to the deploy skill.

## Template

```yaml
---
# Why it's here, plus any one-time setup. See <upstream self-hosting docs URL>
<name>:
  description: <one-line purpose, no versions>

  no_log: true                # only when it references bws_secrets

  files:
    - dest: "{{ services_data_dir }}/<name>/data"

  containers:
    - image: <registry>/<image>:<exact tag>
      labels:
        traefik.enable: "true"
        traefik.http.services.<name>.loadbalancer.server.port: "<port>"
      volumes:
        - "{{ services_data_dir }}/<name>/data:/data"
      env:
        SECRET: "{{ bws_secrets.<NAME>_SECRET }}"

  gatus:                      # optional: Gatus checks, only on the vps
    endpoints:
      - name: <name>
        group: services
        url: "https://<name>.{{ services_domain }}"
        conditions: ["[STATUS] == 200"]
```

## Gotchas

- **`image:`**: write it as `image: repo:tag` on one line. That's the only form Renovate's regex manager tracks. Leave the digest off: Renovate's pin-digest PR adds it. Registry tags often drop the release's `v` (atuin: `18.24.1`).
- **Several containers**: each needs a unique `name`. That name is also its default hostname and how the containers reach each other on the `services` network (`http://karakeep-meilisearch:7700`).
- **`vars:`**: only for a value used more than once (karakeep's meili key and URL, restic's password). Name it with the Service as prefix: vars become host-wide facts that outlive the Service. Use a value needed only once inline as `bws_secrets.<KEY>`.
- **Defaults**: `services_container_defaults` already sets PUID, PGID, TZ, restart, logging and the network. Add only what differs.
- **`network_mode: host`**: the container leaves the `services` network, and Traefik reaches it through `host.docker.internal`.
- **Image runs as a fixed UID**: give its data dir that `owner`/`group` in `files:` (aven: 65532). Find it on the Host, since the laptop's Docker is usually off: `ssh <host> docker run --rm --entrypoint id <image>`.
- **Synced workspace**: mount `{{ services_workspace_dir }}` (the laptop's workspace, synced by syncthing), read-only unless the Service must write to it. Never mount it from inside syncthing's data dir.
- **Home Host** (a `local` Host such as nas-svc): no Traefik labels or `gatus:` key. Publish the port (`ports: ["<port>:<container port>"]`) and add `ingress: {port: <port>}`, as whoami does. The Service is then at `https://<name>.svc.sbbh.cloud`, routed by HAProxy on OPNsense. After its Deploy, it needs a run of `ansible/playbooks/opnsense.yaml` (laptop only) and a Deploy of `gatus`, which generates its check: a keyless GET of `/` expecting 200. When `/` needs a login or redirects, set `ingress: {port: <port>, check: <path>}` to a path that answers 200 without one, as crawl4ai does.
- **Private Service**: a file that must stay out of the public repo is `<name>.private.yaml`, which is gitignored and lives only in the main checkout. Its name still goes in `inventory.yml` and in `services_private` (`group_vars/all/services.yaml`), and only the main checkout can Deploy it or run opnsense.yaml. The services role skips a `services_private` Assignment whose file is missing, so CI, Semaphore and worktrees leave it alone; any other missing file still fails.
- **Hostname override**: set a `traefik.http.routers.<name>.rule` label, as opengym does.
- **HTTPS-only backend**: add a `traefik.http.services.<name>.loadbalancer.server.scheme: https` label, as unifi does. For a self-signed cert, also `traefik.http.services.<name>.loadbalancer.serversTransport: skip-verify@file`.
- **`gatus:`**: Gatus `endpoints` and `external-endpoints` in Gatus's own schema, written to Gatus's config dir by the Service's Deploy. Endpoints without `alerts` get Pushover with send-on-resolved. The `group` and `name` make the endpoint key (`<group>_<name>`), which must be unique across Services and is the push URL for an external endpoint.
- **Leave out** Service names that clash with a Step tag (`pre-tasks`, `files`, `containers`, `post-tasks`) or with `all`/`always`.
