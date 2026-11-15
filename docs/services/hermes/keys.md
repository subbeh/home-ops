---
covers:
  - ansible/services/hermes.yaml
  - ansible/services/tasks/hermes-profile-keys.yaml
---
# Keys and secrets

Every Hermes secret lives in Bitwarden Secrets Manager (BWS), like the rest of the repo's. They reach Hermes two ways: the container env, for what only the default Profile uses, and each Profile's `.env`, for the provider and tool keys.

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
| `web` | `HERMES_TAVILY_API_KEY`, `HERMES_FIRECRAWL_API_KEY` | `TAVILY_API_KEY` for page reads, `FIRECRAWL_API_KEY` as an unused fallback (plus `SEARXNG_URL`, not a secret: [README.md](README.md#web-search-and-page-reads)) |
| `aven` | `AVEN_MCP_TOKEN` | `AVEN_MCP_TOKEN`, the bearer token for the aven MCP server ([README.md](README.md#tasks-over-mcp)) |
| `opengym` | `HERMES_OPENGYM_MCP_TOKEN` | `OPENGYM_MCP_TOKEN`, a scoped openGym token that writes only Workouts and Plans & routines for the openGym MCP server ([README.md](README.md#workouts-over-mcp)) |
| `googlehealth` | `HERMES_GOOGLE_HEALTH_CLIENT_ID`, `HERMES_GOOGLE_HEALTH_CLIENT_SECRET`, `HERMES_GOOGLE_HEALTH_REFRESH_TOKEN` | `GOOGLE_HEALTH_CLIENT_ID`, `GOOGLE_HEALTH_CLIENT_SECRET`, `GOOGLE_HEALTH_REFRESH_TOKEN`: health's own Google Cloud OAuth client and the refresh token for read-only Fitbit data, read by the googlehealth plugin ([profiles.md](profiles.md#the-health-profile)) |
| `semaphore` | `HERMES_OPS_SEMAPHORE_TOKEN` | `HERMES_OPS_SEMAPHORE_TOKEN`, the `hermes-ops` Semaphore user's token, read by the homelab plugin ([profiles.md](profiles.md#the-homelab-plugin)) |
| `github` | `HERMES_GITHUB_ACTIONS_TOKEN` | `GITHUB_ACTIONS_TOKEN`, a fine-grained token for all the user's repositories with Actions, Issues and Pull requests: read, for ops' actions-failures cron job and the morning brief's PRs and issues ([profiles.md](profiles.md#cron-jobs)). It expires within 366 days, since the `wainmann` org refuses longer-lived tokens: renew it in BWS and Deploy before then |
| `vault` | none | `WIKI_PATH=/vault`, where the `llm-wiki` skill finds the vault, and `HERMES_WRITE_SAFE_ROOT=/opt/data:/vault`, so the file tools may write there; neither is a secret ([vault.md](vault.md#which-profiles-use-it)) |
| `discord` | `HERMES_DISCORD_BOT_TOKEN` | `DISCORD_BOT_TOKEN`, the bot token from the container env again, for the quota-alerts cron job's `hermes send`: cron strips bot tokens from a script's env, and `hermes send` falls back to the `.env` ([kanban.md](kanban.md#quota-alerts)) |

`hermes_profiles` says which Key sets each Profile gets. Every Profile gets `model` and `web`, except `ops`, which has no web tools and gets `model`, `semaphore` and `github`. Only default gets `aven` and `discord`, default and ops get `github`, default and health get `opengym`, and only health gets `googlehealth`. Default and the Kanban Profiles get `vault`; ops and health don't.

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

### Renewing the Google Health refresh token

The health Profile's refresh token lapses after about six months unused, or when you revoke it in your Google Account. The googlehealth tools then fail with `invalid_grant`. The OAuth client stays valid, so only the token changes:

1. Open the [OAuth Playground](https://developers.google.com/oauthplayground). Under the gear icon, tick **Use your own OAuth credentials** and paste the client ID and secret, `HERMES_GOOGLE_HEALTH_CLIENT_ID` and `HERMES_GOOGLE_HEALTH_CLIENT_SECRET` in BWS.
2. In Step 1, paste the three scopes, separated by spaces, and **Authorize APIs**:
   `https://www.googleapis.com/auth/googlehealth.sleep.readonly https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly`
3. Sign in with the Google account your Fitbit is linked to. Past the unverified-app warning (**Advanced**, then **Go to ...**), tick **every** scope's checkbox: Google lets you grant some and not others.
4. In Step 2, **Exchange authorization code for tokens**, and copy the refresh token into `HERMES_GOOGLE_HEALTH_REFRESH_TOKEN` in BWS.
5. Deploy hermes, then check: `docker exec hermes hermes -p health chat --oneshot -Q -q "My steps and sleep for the last 3 days, with sources."`. `403 MISSING_OAUTH_SCOPE` on one data type means its checkbox was left unticked: repeat from step 2.

If the Google Cloud consent screen ever drops back to Testing, Google expires every refresh token after 7 days: publish it to **In production** again (Google Auth Platform, Audience).

## Adding a key

1. Add it to BWS (through the dotfiles bws sync, as for any new secret; see [deploy.md](../../runbooks/deploy.md)).
2. Add it to a Key set in `hermes.yaml`, or add a new Key set and list it for the Profiles that need it.
3. Deploy hermes.
