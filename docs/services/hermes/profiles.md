---
covers:
  - ansible/services/hermes.yaml
  - ansible/services/data/hermes/actions-failures.py
  - ansible/services/data/hermes/go-usage.py
---
# Profiles and models

A **Profile** is one persona of Hermes: its own model, persona, memory, skills, sessions, cron jobs and keys. Every Profile runs inside the one `hermes` container, through the one gateway and Discord bot. Upstream: [profiles](https://hermes-agent.nousresearch.com/docs/user-guide/profiles).

## The Profiles

| Profile | Job | Model | Tools |
|---|---|---|---|
| `default` | The assistant you chat with in Discord; owns the Discord settings | deepseek-v4.1-flash | The default toolsets, web search included, plus aven tasks over MCP ([README.md](README.md#tasks-over-mcp)) and the planning and focus skills ([README.md](README.md#planning-and-focus-skills)) |
| `orchestrator` | Splits a Kanban goal into cards, routes them, writes the final summary | deepseek-v4.1-flash | Board only: kanban and memory, so it routes work instead of doing it |
| `researcher` | Gathers facts with web search, cites sources | glm-5.3-flash | Default toolsets |
| `writer` | Turns research notes into the deliverable | deepseek-v4-pro | Default toolsets |
| `reviewer` | Checks the writer's work against the card: PASS or FAIL with a punch-list, never edits | mimo-v2.6-pro | Default toolsets |
| `ops` | The homelab specialist, in #ops: checks status and logs, proposes changes as repo edits and Deploys, never makes them live by hand | deepseek-v4.1-flash | Default toolsets without web and browser on Discord, plus the [homelab plugin](#the-homelab-plugin) |

The four Kanban Profiles have no Discord bot of their own: they only work on cards ([kanban.md](kanban.md)). Each has a description, which the orchestrator reads to route work, and a `SOUL.md` persona. Hermes drafted both from a prompt and the user approved them. The default Profile keeps the stock `SOUL.md`, and its `memories/USER.md` holds the user's profile (timezone, location, reply style, brief topics, workday, personal day and quiet hours), which Hermes wrote from a Discord chat. To change it, tell Hermes in Discord: it rewrites the file itself, within `memory.user_char_limit`. The file goes to the model provider every turn.

`ops` is reached through the #ops route ([README.md](README.md#how-a-message-flows)), not the board. It has no web or browser tools because it will hold Deploy power, so no web page should reach its context; it names what to look up instead. Its `SOUL.md` was drafted for it and approved by the user.

### The homelab plugin

Tools that let ops answer "what's down?" or "how did the last Deploy go?" from the homelab itself, and start a Deploy once the user approves it. The plugin is in the repo at [`ansible/services/data/hermes/homelab/`](../../../ansible/services/data/hermes/homelab/), and each Deploy of hermes copies it into ops' own `plugins/` dir, so no other Profile can load it. It is enabled once by hand (step 9 of the `hermes.yaml` header).

| Tool | Reads |
|---|---|
| `homelab_status` | Gatus: each endpoint up or down, recent results, the last failure's errors |
| `homelab_tasks`, `homelab_task_output` | Semaphore: recent tasks (each one a Deploy) and a task's Ansible output |
| `homelab_containers`, `homelab_container_logs` | Docker, through the [socket proxy](safety.md#the-docker-socket-proxy): the container list and a container's logs |
| `homelab_deploy` | Starts the Semaphore `services` template for one Service, after approval in Discord ([safety.md](safety.md#the-deploy-tool)), and returns the task id and its Semaphore link; ops follows it with `homelab_tasks` and may leave the link out of its reply |

The plugin reads `HERMES_OPS_SEMAPHORE_TOKEN` from ops' `.env` on each call ([keys.md](keys.md)), so the token never reaches the terminal or the model. Gatus and Semaphore are reached over the services network, without a login for Gatus. `scripts/hermes-homelab.test.py` (`just docs-test`) checks the response parsing and the Deploy gate; `hermes plugins doctor ansible/services/data/hermes/homelab --ci` checks that it loads.

Why these models: researcher does many tool calls, so it gets the model with a large request allowance. The reviewer is from a different model family than the writer, so it doesn't favour its own family's output.

The reviewer re-reads its whole context on every call, so cached-read price sets its cost. On kimi-k3.1-pro one review took 55 calls at about 150k cached tokens each, and reviews used about $5.90 of the week's $8. mimo-v2.6-pro prices cached reads at about 2% of Kimi's. For a high-stakes review, put one card back on Kimi with `hermes kanban set-model <card> kimi-k3.1-pro --provider opencode-go`.

Its `agent.max_turns` is 40, where the other Profiles keep 500. A worker that reaches the cap is told to answer without tools, so it can't call `kanban_complete`: the card counts as a protocol violation and reruns, up to 3 in a row, and the review is lost. So its `SOUL.md` spot-checks about 5 citations and finishes by turn 30.

## Cron jobs

A cron job runs a prompt on a schedule, each run in a fresh session, and posts the answer to its delivery target. A pre-check script can run first: when its last stdout line is `{"wakeAgent": false}` the run ends there, with no model call, and otherwise its output becomes part of the prompt. Upstream: [cron](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron). Jobs live in each Profile's `cron/` dir, created by hand ([`hermes.yaml`](../../../ansible/services/hermes.yaml)'s header has the commands).

| Job | Profile | Schedule | What it does |
|---|---|---|---|
| `actions-failures` | `ops` | every 15 min | Posts one diagnosis in #ops per GitHub Actions run of home-ops that failed since the last check |
| `quota-alerts` | `default` | every 15 min | Posts a notice for a Kanban card stuck on the usage limit, a goal's third or later review round, or a spend spike. No model call ([kanban.md](kanban.md#quota-alerts)) |
| `morning-brief` | `default` | daily 06:30 | Posts the weather, the last day's headlines on the USER.md topics, today's aven tasks and OpenCode Go usage to the home channel, through the `morning-brief` skill ([README.md](README.md#planning-and-focus-skills)), as a plain message: the job's `attach_to_session: false` keeps it out of a thread |
| `plan-day` | `default` | daily 06:45 | Starts the [plan-day skill](README.md#planning-and-focus-skills) in the home channel |
| `wrap-up` | `default` | daily 21:00 | Starts the wrap-up skill in the home channel |

`actions-failures` runs [`actions-failures.py`](../../../ansible/services/data/hermes/actions-failures.py), which Ansible ships into ops' `scripts/` dir. It lists the repo's latest 50 finished runs, keeps the failed ones it hasn't seen (a re-run that fails again counts as new), and prints each with the last 60 log lines up to its error, so ops diagnoses it in one model call. Its first run only records what already failed. Runs from fork PRs are left out, since their logs are a stranger's text. When GitHub is down it stays silent; a rejected token fails the job, and Hermes posts the error.

**Not posted yet:** Hermes doesn't deliver a routed Profile's cron output once that Profile has had a local session ([upstream #144455](https://github.com/NousResearch/hermes-agent/issues/144455)): the run's record says `platform 'discord' not configured/enabled`. Until a Hermes release fixes it, each diagnosis is written only to `/opt/data/profiles/ops/cron/output/<job id>/` and `hermes -p ops cron list` shows the failed delivery.

**Private threads:** with `cron.mirror_delivery` on, a cron run in the home channel opens a new thread so a reply continues the run's session. Hermes's Discord adapter creates it without a starter message, which Discord makes a private thread: only the bot and server admins can open it, and it never shows in the channel. So the bot is denied **Create Private Threads** in the home channel: the direct create fails, and Hermes falls back to posting a seed line (`🧵 Hermes handoff: …`) and opening a public thread from it. A job with `attach_to_session: false` skips the thread and posts a plain message.

`morning-brief` runs [`go-usage.py`](../../../ansible/services/data/hermes/go-usage.py) as its pre-check script, which Ansible ships into default's `scripts/` dir. It reads the plan's usage meters and this billing month's spend per model from the OpenCode console API, the one behind the console's Billing drawer, with default's `OPENCODE_GO_API_KEY` from `/opt/data/.env`, and prints them for the brief, flagging anything over 75%. The API is undocumented, so a change on OpenCode's side shows up as "usage unavailable" in the brief rather than a missing brief: the script prints that on any failure. A manual `/morning-brief` has no pre-check, so the skill runs the script in the terminal.

Cron scripts get a scrubbed env, so `GITHUB_ACTIONS_TOKEN` (the `github` Key set, [keys.md](keys.md)) reaches the script through ops' `terminal.env_passthrough`. That also hands it to ops' terminal in chats: a read-only token for a public repo's Actions.

`plan-day` and `wrap-up` follow the personal day in USER.md (06:30-21:00, every day: the tasks are for life outside work), with `plan-day` 15 minutes after the morning brief. Each opens with the skill's first question, and `cron.mirror_delivery` in the default Profile's `config.yaml` makes a reply to it continue with that message in context. To move them, tell Hermes the new day: a MEMORY.md entry tells it to edit both jobs' schedules to match, outside quiet hours.

## What Profiles share, and what they don't

- **Own**: `config.yaml`, `SOUL.md`, memory, skills, sessions, `.env` keys, cron jobs. The default Profile's home is the data dir itself (`/opt/data`); each other Profile's is `/opt/data/profiles/<name>`.
- **Shared**: the container, its filesystem, the gateway and the Discord bot. One Profile's terminal can read another Profile's files and keys; [safety.md](safety.md) says what that means.
- **Discord settings** stay in the container env and belong to the default Profile only.
- **Routes** (`gateway.profile_routes`) live in the default Profile's `config.yaml`.

## Models and costs

All Profiles use provider `opencode-go`. [OpenCode Go](https://opencode.ai/docs/go/) is a subscription (Go Plus here) counted in dollars at per-token prices. OpenCode's page lists a monthly allowance per model, with 5-hour and weekly caps at 20% and 50% of it, so the cheap model with the largest allowance does the everyday work.

Confusing part: what actually blocks is one meter per window for the whole plan, shared by every model: 5 hours, the week (resets Monday 00:00 UTC) and the billing month (resets on the subscription date, not the 1st). The console's `go/status` API shows each meter's limit, use and reset time, and the morning brief prints them ([cron jobs](#cron-jobs)). When the weekly meter ran out (`GoUsageLimitError`, `limitName: weekly`), every Profile stopped, whichever model it runs.

**Subagents.** When the default Profile delegates a subtask, the advanced-delegation plugin picks the model by route ([upstream](https://github.com/NousResearch/hermes-official-plugins/tree/main/advanced-delegation)):

- `fast` (the default): deepseek-v4.1-flash, for lookups and research.
- `deep`: deepseek-v4-pro, for hard reasoning.

Subagents don't spawn subagents of their own (depth 1). `hermes delegation config --show` lists the routes.

**Auxiliary tasks.** Hermes runs side tasks on a model of their own (`auxiliary.<task>` in each Profile's `config.yaml`). On `auto`, a task uses the Profile's main model, so writer and reviewer would spend their small allowances on compaction and titles. In every Profile, compression (at low reasoning effort), title generation, approval and the background review run on deepseek-v4.1-flash instead. Vision runs on glm-5.3-flash, since writer's model reads no images. The other auxiliary tasks stay on `auto`. To see which models a Profile's calls used, side tasks included, run `hermes -p <profile> insights --days 1` and read "Models Used".

**Traces and prices.** The langfuse plugin sends a trace of every main-agent model call to Langfuse Cloud (auxiliary calls aren't traced), with metadata only (`HERMES_LANGFUSE_CAPTURE: metadata`), so chat content stays off it. Hermes knows no prices for opencode-go and sends no cost, so Langfuse computes it from its own model definitions (Settings > Models), one per model at OpenCode Go's off-peak rates. Because Go's allowance is counted in dollars at those rates, the cost Langfuse shows is the allowance used. A definition prices only calls made after it exists, and Langfuse doesn't backfill, so earlier calls show no cost.

Confusing part: DeepSeek models bill double during peak hours, but Langfuse has one price per model, so peak-hour calls show at half their real cost. The response carries the exact charge, but Hermes doesn't read it yet.

To read traces through the API, use `/api/public/v2/observations` with a time range and `fields=core,basic,usage,model`. Without `model` and `usage` in `fields`, those come back empty, which looks like missing data.

**Fallback.** When a Profile's model fails a turn (its cap, a rate limit, a 5xx, an unknown model), Hermes retries that turn on another Go model from a different family, and says so in the reply. Fallback is per turn: the next message tries the Profile's own model first again. It doesn't help once the shared weekly cap is hit, since the fallback model is refused too.

- **glm-5.3-flash**: default, ops, orchestrator, writer and reviewer. Reviewer's fallback still differs from writer's family.
- **deepseek-v4.1-flash**: researcher, which runs GLM itself.
- **Subagents**: the `fast` and `deep` routes (both DeepSeek) fall back to glm-5.3-flash through `delegation.fallback_providers` in default's `config.yaml`. A route with no `fallback_providers` of its own inherits it.

Each Profile keeps its chain in `fallback_providers` in its own `config.yaml`. A Profile cloned from default copies glm-5.3-flash ([Adding a Profile](#adding-a-profile)). `hermes -p <name> fallback list` shows a Profile's chain.

To check it, ask for a model OpenCode Go doesn't have: `docker exec hermes hermes chat --oneshot --provider opencode-go -m no-such-model -q "Reply with ok."` should answer from glm-5.3-flash, with a "Model fallback" notice. A bad `OPENCODE_GO_API_KEY` in the exec env doesn't work as a test, since the Profile's `.env` wins.

## Adding a Profile

1. Check `docker exec hermes hermes kanban list` for running cards, since step 4 restarts the container ([running.md](running.md)).
2. `docker exec -it hermes hermes profile create <name> --clone`. `--clone` copies default's config, skills and `.env`, including the hardening from setup step 17 ([safety.md](safety.md#hard-deny-rules)).
3. Set its model (`docker exec -it hermes hermes -p <name> model`), and write its description and `SOUL.md`. The clone copies default's glm-5.3-flash fallback. If the Profile's own model is GLM, set another family with `hermes -p <name> config set fallback_providers '[{provider: opencode-go, model: <model>}]'`.
4. List it under `hermes_profiles` in [`hermes.yaml`](../../../ansible/services/hermes.yaml) with the Key sets it needs, commit, and Deploy hermes. The Deploy writes its keys ([keys.md](keys.md)).
5. In its `.env`, delete any key outside the managed block that it shouldn't have: the clone copied default's.
6. Add one line for each lasting setting to the `hermes.yaml` header, and a row to the table above.
7. To reach it from Discord, add a `gateway.profile_routes` entry in default's `config.yaml`. Kanban Profiles need no route.
