---
covers:
  - ansible/services/hermes.yaml
  - ansible/services/tasks/hermes-profile-keys.yaml
---
# Keys and secrets

Every Hermes secret lives in Bitwarden Secrets Manager (BWS), like the rest of the repo's. They reach Hermes two ways: the container env, for what only the default Profile uses, and each Profile's `.env`, for the provider and tool keys.

One exception: the Claude login for the default Profile's fallback ([profiles.md](profiles.md#models-and-costs)). It's an OAuth login the Claude Code CLI keeps and refreshes in `/opt/data/.claude`, so it can't live in BWS. If it expires, run `claude auth login` again as the hermes user. Keep `ANTHROPIC_*` keys and endpoints out of every env: the plugin refuses to run when it inherits one.

## Container env (default Profile only)

| BWS key | Used for |
|---|---|
| `HERMES_DISCORD_BOT_TOKEN` | The Discord bot |
| `HERMES_DISCORD_ALLOWED_USERS` | Who the bot answers, and who can press approval buttons |
| `HERMES_DASHBOARD_PASSWORD` | Dashboard basic auth (user `admin`) |
| `HERMES_DASHBOARD_SECRET` | Signs dashboard sessions, so logins survive a restart (`openssl rand -hex 32`) |

## Key sets, written into each Profile's `.env`

A **Key set** is a named group of secrets a Profile may get. [`hermes.yaml`](../../../ansible/services/hermes.yaml) defines them under `hermes_key_sets`:

| Key set | BWS keys | Lands in `.env` as |
|---|---|---|
| `model` | `HERMES_OPENCODE_GO_API_KEY`, `HERMES_LANGFUSE_PUBLIC_KEY`, `HERMES_LANGFUSE_SECRET_KEY` | `OPENCODE_GO_API_KEY`, `HERMES_LANGFUSE_PUBLIC_KEY`, `HERMES_LANGFUSE_SECRET_KEY` (plus `HERMES_LANGFUSE_CAPTURE`, not a secret) |
| `web` | `HERMES_FIRECRAWL_API_KEY` | `FIRECRAWL_API_KEY` |
| `aven` | `AVEN_MCP_TOKEN` | `AVEN_MCP_TOKEN`, the bearer token for the aven MCP server ([README.md](README.md#tasks-over-mcp)) |
| `semaphore` | `HERMES_OPS_SEMAPHORE_TOKEN` | `HERMES_OPS_SEMAPHORE_TOKEN`, the `hermes-ops` Semaphore user's token, read by the homelab plugin ([profiles.md](profiles.md#the-homelab-plugin)) |
| `github` | `HERMES_GITHUB_ACTIONS_TOKEN` | `GITHUB_ACTIONS_TOKEN`, a fine-grained token for the home-ops repo with Actions: read, for the actions-failures cron job ([profiles.md](profiles.md#cron-jobs)) |

`hermes_profiles` says which Key sets each Profile gets. Every Profile gets `model` and `web`, except `ops`, which has no web tools and gets `model`, `semaphore` and `github`. Only default gets `aven`.

On each Deploy, the [`hermes-profile-keys`](../../../ansible/services/tasks/hermes-profile-keys.yaml) post-task:

1. Finds each listed Profile's home (`/opt/data` for default, `/opt/data/profiles/<name>` for the rest). A listed Profile that doesn't exist yet is skipped.
2. Writes its keys as a marked block at the end of its `.env` (`# BEGIN ANSIBLE MANAGED ...`), mode `0600`. Lines outside the block, which Hermes itself writes, stay untouched.
3. Restarts hermes when any block changed, since default and the plugins read `.env` only at startup.

So BWS is the only source, a rotated key reaches every Profile on the next Deploy, and a Profile gets only the keys it needs.

## Why not the container env for everything

Under the multiplexed gateway, a non-default Profile reads secrets only from its own `.env`, never from the container env ([upstream issue #147922](https://github.com/NousResearch/hermes-agent/issues/147922)). An OpenCode Go key in the container env worked for default and silently failed for every Kanban Profile. Once upstream fixes that, the container env would be simpler.

A managed `.env` that Hermes merges into every Profile (`HERMES_MANAGED_DIR`) was also considered. It would give every Profile every key, and the image's own boot hook says that merge may have been reverted upstream.

## Why not the dashboard

The dashboard's Providers > API keys page saves a key into the active Profile's `.env`, outside the managed block. Such a key:

- isn't in BWS, so a rotation never reaches it;
- is copied once into every Profile cloned later, and goes stale there too;
- loses to the managed block anyway, because the block comes last in the file and the last value wins.

So never save keys in the dashboard. If one is there, delete its line from the `.env`.

## Rotating a key

1. Change the value in BWS.
2. Deploy hermes ([running.md](running.md)). The block changes, and hermes restarts with the new key.

## Adding a key

1. Add it to BWS (through the dotfiles bws sync, as for any new secret; see [deploy.md](../../runbooks/deploy.md)).
2. Add it to a Key set in `hermes.yaml`, or add a new Key set and list it for the Profiles that need it.
3. Deploy hermes.
