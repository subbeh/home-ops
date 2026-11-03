---
covers:
  - ansible/services/hermes.yaml
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
 │    ├─ ops            the homelab specialist, in #ops  │
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
- **Plugins**: installed into the data dir, so they survive a container recreate. hermes-memory-wiki adds long-term notes, langfuse sends traces to Langfuse Cloud, advanced-delegation picks the model for subagents, and claude-subscription-directsdk gives the default Profile its Claude fallback ([profiles.md](profiles.md#models-and-costs)). The ops Profile also gets the homelab plugin, which lives in this repo ([profiles.md](profiles.md#the-homelab-plugin)).
- **Socket proxy**: the separate `docker-socket-proxy` Service lets Hermes list containers and read their logs, and nothing else. See [safety.md](safety.md).
- **Tasks**: the default Profile reads and changes your aven tasks over MCP. See [Tasks over MCP](#tasks-over-mcp).

Why one container and not one per bot: the vps has little memory free and no swap, and each extra gateway costs about 400 MiB. So every new bot is a new Profile, never a new container. The price is weaker isolation between Profiles, covered in [safety.md](safety.md).

## How a message flows

1. You post in Discord. Only the users in `DISCORD_ALLOWED_USERS` get an answer.
2. In the home channel (`DISCORD_HOME_CHANNEL`), Hermes answers without being mentioned and opens a thread for each conversation. Scheduled messages are delivered there too. Elsewhere, mention the bot.
3. The gateway runs in multiplexed mode: one bot serves several Profiles. It checks `gateway.profile_routes` in the default Profile's `config.yaml` for a route matching the channel, thread or user. The most specific match wins, and a channel route also covers that channel's threads.
4. One route exists: #ops and its threads go to the **ops** Profile. Every other message falls to the **default** Profile: routing isn't a deny list, so the Discord allowlist is what keeps strangers out.
5. A route whose target Profile doesn't exist makes the gateway reject the message. It doesn't fall back to default.
6. That Profile answers. It may spawn subagents on cheaper or stronger models ([profiles.md](profiles.md)), and it asks you in Discord before any dangerous command ([safety.md](safety.md)).
7. `/kanban create --triage "<goal>"` hands a goal to the Kanban team instead. Results come back as notices in the same channel ([kanban.md](kanban.md)).

Upstream: [multi-profile gateways](https://hermes-agent.nousresearch.com/docs/user-guide/multi-profile-gateways).

## Tasks over MCP

The default Profile manages aven tasks through the `aven-mcp` container, which runs beside the sync server in the `aven` Service ([`aven.yaml`](../../../ansible/services/aven.yaml)):

- **A device of its own**: `aven-mcp` runs `aven mcp --http --sync`, a synced aven device with its own database, so tasks Hermes creates show up on your other devices, and yours reach Hermes within the 30-second sync interval. The sync server alone can't serve MCP: it only relays encrypted changes and can't read a task.
- **Connection**: Hermes reaches `http://aven-mcp:3747/mcp` over the services network. No port is published. Hermes's `config.yaml` sends `Authorization: Bearer ${AVEN_MCP_TOKEN}`, and Hermes fills that in from the Profile's `.env` (the `aven` Key set in [keys.md](keys.md)).
- **Scope**: Hermes should use only the `default` aven workspace, but aven can't enforce that: the token gives full access to every workspace, with no read-only mode, and the vps device stores all of them, work included. So the limit is soft: the server defaults to `default`, Hermes isn't given the `list_workspaces` tool, and its memory holds the rule. Only the default Profile gets the token.

The join and config steps are in `aven.yaml`'s header.

## Planning and focus skills

Four skills in the default Profile help start the day and start and finish tasks. Three of them work on aven tasks in the default workspace only, and their tone is direct and warm: no guilt, no streaks, never a wall of overdue items.

- **plan-day**: asks about energy, then helps pick 1-3 tasks for today, each with a two-minute first step. Picks get today's due date and a note with that step. It names at most one stalled task (active, no update or note for 3+ days).
- **start-task**: gives one ~2-minute first step and offers a 10-25 minute session. A one-off cron job (`in <N>m`) posts the single check-in to the thread at the end; nothing is sent during the session. With no task named it asks which one.
- **morning-brief**: the weather at the USER.md location and the last day's 1-2 top stories per USER.md news topic, with links. Tell Hermes a new location or topic and the next brief follows it.
- **wrap-up**: marks today's finished picks done, moves carry-overs to tomorrow and clears the due date of dropped ones. On Fridays it adds a recap of the week's done tasks.

morning-brief, plan-day and wrap-up also start on their own each day, at 06:30, 06:45 and 21:00 ([cron jobs](profiles.md#cron-jobs)). Run one by typing `/plan-day`, `/start-task <task>`, `/wrap-up` or `/morning-brief` as a message, or through Discord's `/skill` command: Hermes registers one `/skill` command with autocomplete instead of one command per skill, so these don't show in the command picker on their own. The skills live only on the vps, in `/opt/data/skills/productivity/` (setup steps 11 to 13 in [`hermes.yaml`](../../../ansible/services/hermes.yaml)'s header). After editing one, run `/reload-skills` in Discord.

## Read next

| Page | Answers |
|---|---|
| [profiles.md](profiles.md) | Which Profiles exist, their models and jobs, cron jobs, model costs and Langfuse, how to add a Profile |
| [keys.md](keys.md) | How keys get from Bitwarden into each Profile, and why not through the dashboard |
| [kanban.md](kanban.md) | How a goal becomes cards, the review loop, Discord notices, what a Deploy does to running cards |
| [safety.md](safety.md) | Approvals, the socket proxy, resource limits, what one Profile can see of another |
| [running.md](running.md) | Deploying hermes, rotating a key, reading logs, common failures |

The one-time setup steps (picking the model, installing plugins, ...) are the checklist in [`hermes.yaml`](../../../ansible/services/hermes.yaml)'s header. Hermes owns its `config.yaml` and edits it itself, so Ansible never writes it: those settings are made by hand and recorded in that header.
