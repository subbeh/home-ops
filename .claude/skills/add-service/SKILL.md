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

  vars:                       # secrets fetched once; prefix with the Service name
    <name>_secret: "{{ bws_secrets.<NAME>_SECRET }}"

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
        SECRET: "{{ <name>_secret }}"
```

## Gotchas

- **`image:`**: write it as `image: repo:tag` on one line. That's the only form Renovate's regex manager tracks. Leave the digest off: Renovate's pin-digest PR adds it. Registry tags often drop the release's `v` (atuin: `18.24.1`).
- **Several containers**: each needs a unique `name`. That name is also its default hostname and how the containers reach each other on the `services` network (`http://karakeep-meilisearch:7700`).
- **Defaults**: `services_container_defaults` already sets PUID, PGID, TZ, restart, logging and the network. Add only what differs.
- **`network_mode: host`**: the container leaves the `services` network, and Traefik reaches it through `host.docker.internal`.
- **Image runs as a fixed UID**: give its data dir that `owner`/`group` in `files:` (aven: 65532). Find it on the Host, since the laptop's Docker is usually off: `ssh <host> docker run --rm --entrypoint id <image>`.
- **Hostname override**: set a `traefik.http.routers.<name>.rule` label, as opengym does.
- **Leave out** Service names that clash with a Step tag (`pre-tasks`, `files`, `containers`, `post-tasks`) or with `all`/`always`.
