---
covers:
  - ansible/services/hermes.yaml
  - ansible/services/tasks/hermes-*.yaml
  - ansible/services/docker-socket-proxy.yaml
---
# Hermes

[Hermes Agent](https://hermes-agent.nousresearch.com/docs/) is a self-hosted AI assistant. Here it is the `hermes` Service on the vps: you talk to it in Discord, it runs on [OpenCode Go](https://opencode.ai/docs/go/) models, and a small team of AI workers takes on bigger goals through a Kanban board. These pages explain how it is set up and why, for someone who knows Docker but not Hermes.

## The pieces

```text
 Discord ── one bot ──┐
                      ▼
 ┌─────────────── hermes container (vps) ───────────────┐
 │  gateway ── routes each message to a Profile          │
 │    ├─ default        the assistant you chat with      │
 │    ├─ orchestrator ┐                                  │
 │    ├─ researcher   │ the Kanban team: they work on    │
 │    ├─ writer       │ cards, never chat in Discord     │
 │    └─ reviewer     ┘                                  │
 │  dashboard (port 9119) ◄── traefik ◄── hermes.vps.sbbh.cloud
 │  plugins: memory wiki, Langfuse traces, delegation    │
 │  /opt/data: every Profile's files, kanban.db          │
 └────────┬──────────────────────────────────────────────┘
          │ /run/docker-proxy/proxy.sock (read-only mount)
 docker-socket-proxy ── container list and logs only ──► Docker
```

- **Container**: one `hermes` container runs everything ([`hermes.yaml`](../../../ansible/services/hermes.yaml)). Its data dir, `/opt/data/hermes/data` on the vps, is `/opt/data` inside, and restic backs it up hourly with every other Service.
- **Gateway**: the long-running Hermes process (`gateway run`). It holds the Discord connection, runs each conversation and dispatches Kanban cards.
- **Profile**: one persona of Hermes, with its own model, persona (`SOUL.md`), memory, skills and keys. All Profiles live in the one container and share its filesystem and its Discord bot. See [profiles.md](profiles.md).
- **Dashboard**: Hermes's web UI for sessions, config and logs, at <https://hermes.vps.sbbh.cloud> behind basic auth.
- **Plugins**: installed into the data dir, so they survive a container recreate. hermes-memory-wiki adds long-term notes, langfuse sends traces to Langfuse Cloud, and advanced-delegation picks the model for subagents.
- **Socket proxy**: the separate `docker-socket-proxy` Service lets Hermes list containers and read their logs, and nothing else. See [safety.md](safety.md).

Why one container and not one per bot: the vps has little memory free and no swap, and each extra gateway costs about 400 MiB. So every new bot is a new Profile, never a new container. The price is weaker isolation between Profiles, covered in [safety.md](safety.md).

## How a message flows

1. You post in Discord. Only the users in `DISCORD_ALLOWED_USERS` get an answer.
2. In the home channel (`DISCORD_HOME_CHANNEL`), Hermes answers without being mentioned and opens a thread for each conversation. Scheduled messages are delivered there too. Elsewhere, mention the bot.
3. The gateway runs in multiplexed mode: one bot serves several Profiles. It checks `gateway.profile_routes` in the default Profile's `config.yaml` for a route matching the channel, thread or user. The most specific match wins, and a channel route also covers that channel's threads.
4. No route matches today, so every message goes to the **default** Profile. A message that matches no route always falls to default: routing isn't a deny list, so the Discord allowlist is what keeps strangers out.
5. A route whose target Profile doesn't exist makes the gateway reject the message. It doesn't fall back to default.
6. The default Profile answers. It may spawn subagents on cheaper or stronger models ([profiles.md](profiles.md)), and it asks you in Discord before any dangerous command ([safety.md](safety.md)).
7. `/kanban create --triage "<goal>"` hands a goal to the Kanban team instead. Results come back as notices in the same channel ([kanban.md](kanban.md)).

Upstream: [multi-profile gateways](https://hermes-agent.nousresearch.com/docs/user-guide/multi-profile-gateways).

**Planned:** an `ops` Profile for the homelab, reached by posting in a new #ops channel. A `profile_routes` entry will send #ops and its threads to `ops`, and everything else stays on default.

## Read next

| Page | Answers |
|---|---|
| [profiles.md](profiles.md) | Which Profiles exist, their models and jobs, model costs and Langfuse, how to add a Profile |
| [keys.md](keys.md) | How keys get from Bitwarden into each Profile, and why not through the dashboard |
| [kanban.md](kanban.md) | How a goal becomes cards, the review loop, Discord notices, what a Deploy does to running cards |
| [safety.md](safety.md) | Approvals, the socket proxy, resource limits, what one Profile can see of another |
| [running.md](running.md) | Deploying hermes, rotating a key, reading logs, common failures |

The one-time setup steps (picking the model, installing plugins, ...) are the checklist in [`hermes.yaml`](../../../ansible/services/hermes.yaml)'s header. Hermes owns its `config.yaml` and edits it itself, so Ansible never writes it: those settings are made by hand and recorded in that header.
