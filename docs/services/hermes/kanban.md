---
covers:
  - ansible/services/tasks/hermes-kanban-notices.yaml
  - ansible/services/data/hermes/quota-alerts.py
---
# The Kanban team

Hermes's [Kanban board](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban) lets several Profiles work on one goal. A **card** is one task on the board, assigned to one Profile, with a status and a result. Cards live in `/opt/data/kanban.db`. The team is four Profiles: orchestrator, researcher, writer and reviewer ([profiles.md](profiles.md)).

## How a goal becomes cards

1. In the Discord home channel, `/thread name:<goal> message:/kanban create --triage "<goal>"` opens a public thread for the goal and creates its root card from inside it ([Goal threads](#goal-threads)).
2. Triage splits the goal into child cards with dependencies: research first, then writing, then review.
3. After the split, the **orchestrator** owns the root card (`kanban.orchestrator_profile: orchestrator`). It routes each child to a Profile by its description. A child that names no existing Profile goes to researcher (`kanban.default_assignee`).
4. The gateway's dispatcher starts a worker for each card that is ready, one at a time (`kanban.max_in_progress`: [safety.md](safety.md#resource-limits)). The worker runs as its Profile, does the job and hands in its full notes or deliverable as a markdown file listed in `kanban_complete`'s `artifacts`, for Discord ([Notices in Discord](#notices-in-discord)). The card's `result` field goes unused: it reaches neither Discord nor the next worker. A child card's context carries each done parent's summary and `metadata`, each cut short. A card's scratch workspace is deleted when it completes, but Hermes first copies declared artifacts into the card's attachments.
5. Workers never create cards. Follow-ups go in their summary, and the orchestrator plans them.
6. When every child is done, the orchestrator writes a short summary on the root card (what was delivered, what is uncertain, what is left) and closes it.

## The review loop

The reviewer reads the card's acceptance criteria, the writer's output and the researcher's sources. It returns PASS, FAIL or BLOCKED, with a punch-list, and never edits the work.

On FAIL, the orchestrator adds two chained cards: a writer fix, then a reviewer recheck. After two failed rechecks on one deliverable it adds no more: it blocks the root card with kind `needs_input`, giving the latest punch-list and asking the user what to do. Without that cap, one goal looped through three more drafts and spent about $13 in three hours. A blocked card is unblocked only once its cause is fixed, since a card that is still broken just fails again.

`kanban.review_dispatch` is `false`. When true, Hermes runs its own review step on finished cards. Off, the reviewer is an ordinary card and review stays a manual gate.

Review is the costly part of a goal: the reviewer reads everything the others wrote, and re-reads it on every call. So it spot-checks about 5 citations rather than all of them, within a turn cap ([profiles.md](profiles.md)).

## Notices in Discord

The chat that created a goal is subscribed to its cards' events: the channel, or the thread when the goal was created inside one. A subscription has a delivery mode:

- `notify`: a plain notice in that chat, with the card's summary and its result files.
- `notify+wake`: the notice, and the subscribed Profile also takes a turn to act on it.

A notice shows only the card's title and the first line of its summary, cut at 200 characters. The card's result isn't posted. Files reach the channel only as uploads: each path in `kanban_complete`'s `artifacts`, or a file path named in the summary or result. So each worker's SOUL.md tells it to write its full output to a markdown file and list it in `artifacts`. Without that, the researcher once put its whole deliverable in `metadata`, and Discord got a cut-short line.

`/kanban create` always subscribes with `notify+wake`, and cards copy their parent's and creator's subscriptions, so cards the orchestrator adds mid-run get it too. Waking is wrong here: it wakes the default Profile, which has no kanban tools in Discord and digs through `kanban.db` by hand instead of posting the result.

So every Discord subscription is kept on plain `notify`. The [`hermes-kanban-notices`](../../../ansible/services/tasks/hermes-kanban-notices.yaml) post-task, on each Deploy:

- switches any Discord subscription that isn't `notify` to `notify`;
- adds two SQLite triggers on the subscription table, which switch every new or changed Discord subscription to `notify` the moment it's written. A Deploy re-adds a missing trigger, for example after an upgrade rebuilt the table.

Before the gateway first creates `kanban.db`, the task does nothing; the next Deploy adds the triggers.

Confusing part: the triggers depend on `kanban.db`'s schema, which an image Version Bump can change. They are a shortcut until Hermes has a setting for notify-only subscriptions.

## Quota alerts

The `quota-alerts` cron job ([profiles.md](profiles.md#cron-jobs)) runs [`quota-alerts.py`](../../../ansible/services/data/hermes/quota-alerts.py) every 15 minutes. It posts three kinds of notice:

| Notice | When | Where |
|---|---|---|
| Stuck card | A `ready` or `running` card's last 3 finished runs were all rate-limited. Says the Profile, model, how long, the reset time from its worker log, and how to switch model | The goal's thread, else the home channel |
| Review round | A goal with an open card reaches its third reviewer card, and again on each later one | The goal's thread |
| Spend spike | OpenCode Go spend, as Langfuse prices it, over the last 60 minutes passes the limit in the script (`SPEND_LIMIT`). Traces from other tools in the same Langfuse project don't count | The home channel |

A stuck card needs this because Hermes requeues a rate-limited run without counting a failure: the card never blocks, nothing reaches Discord, and it holds a Kanban slot. A stuck card or a spike alerts once per spell, and alerts again only after a normal run, or once spend drops back under the limit. State is in `/opt/data/scripts/quota-alerts.seen.json`.

The job runs with `--no-agent` and posts through `hermes send`, so it makes no model call, even when a notice goes out, and still works when the limit has hit every model. A crash in the script posts its error to the home channel. The script reads `kanban.db` and the Langfuse keys in `/opt/data/.env` directly. Cron strips the bot token from a script's env, so `hermes send` reads it from that `.env` too, written there by the `discord` Key set ([keys.md](keys.md)).

Confusing part: the review count groups cards by their goal's thread, so a goal started in a channel rather than a thread isn't counted, and the spend figure inherits Langfuse's off-peak prices ([profiles.md](profiles.md#models-and-costs)).

## Goal threads

Each goal gets its own thread, so its notices and result uploads stay out of the channel.

- The subscription records the thread the goal was created in, and cards copy it, so every card's notices go there, including cards the orchestrator adds mid-run.
- The native `/kanban` slash command never opens a thread: run in the channel, its notices land in the channel.
- Hermes's `/thread` command does both steps at once: it opens the thread, then runs its `message` there as a command.
- Run it in the home channel. Hermes opens `/thread` without a starter message, which Discord makes a private thread. The bot is denied private threads there ([profiles.md](profiles.md)), so Hermes posts the message in the channel and opens a public thread from it. In other channels the thread is private.
- Running `/kanban create` inside an existing thread works too.

## What a Deploy does to running cards

A Deploy recreates the container, which kills every running worker. What happens next depends on the container's hostname:

- Each card's claim records the hostname of the worker that took it, and the dispatcher reclaims dead workers only for its own hostname.
- Docker's default hostname is the container ID, which changes on every recreate. So after a Deploy, the new dispatcher saw the old claims as another host's and left the cards until their 15-minute claim expired.
- `hostname: hermes` in `hermes.yaml` keeps the name fixed. The dispatcher sees the dead claims as its own and requeues those cards on its next tick.

A requeued card reruns from the start, with no manual step, and the kill counts as a failure toward the card's retry limit. So before a Deploy, check for running cards first ([running.md](running.md)).
