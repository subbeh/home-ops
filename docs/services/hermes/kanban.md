---
covers:
  - ansible/services/tasks/hermes-kanban-notices.yaml
---
# The Kanban team

Hermes's [Kanban board](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban) lets several Profiles work on one goal. A **card** is one task on the board, assigned to one Profile, with a status and a result. Cards live in `/opt/data/kanban.db`. The team is four Profiles: orchestrator, researcher, writer and reviewer ([profiles.md](profiles.md)).

## How a goal becomes cards

1. In Discord, `/kanban create --triage "<goal>"` creates a root card for the goal.
2. Triage splits the goal into child cards with dependencies: research first, then writing, then review.
3. After the split, the **orchestrator** owns the root card (`kanban.orchestrator_profile: orchestrator`). It routes each child to a Profile by its description. A child that names no existing Profile goes to researcher (`kanban.default_assignee`).
4. The gateway's dispatcher starts a worker for each card that is ready, at most two at once (`kanban.max_in_progress`, for memory: [safety.md](safety.md#resource-limits)). The worker runs as its Profile, does the job and hands in its full notes or deliverable as a markdown file listed in `kanban_complete`'s `artifacts`, for Discord ([Notices in Discord](#notices-in-discord)). The card's `result` field goes unused: it reaches neither Discord nor the next worker. A child card's context carries each done parent's summary and `metadata`, each cut short. A card's scratch workspace is deleted when it completes, but Hermes first copies declared artifacts into the card's attachments.
5. Workers never create cards. Follow-ups go in their summary, and the orchestrator plans them.
6. When every child is done, the orchestrator writes a short summary on the root card (what was delivered, what is uncertain, what is left) and closes it.

## The review loop

The reviewer reads the card's acceptance criteria, the writer's output and the researcher's sources. It returns PASS, FAIL or BLOCKED, with a punch-list, and never edits the work.

On FAIL, the orchestrator adds two chained cards: a writer fix, then a reviewer recheck. That repeats until a recheck passes. A blocked card is unblocked only once its cause is fixed, since a card that is still broken just fails again.

`kanban.review_dispatch` is `false`. When true, Hermes runs its own review step on finished cards. Off, the reviewer is an ordinary card and review stays a manual gate.

Review is the costly part of a goal: the reviewer's model is the most expensive one and reads everything the others wrote.

## Notices in Discord

The chat that created a goal is subscribed to its cards' events. A subscription has a delivery mode:

- `notify`: a plain notice in the channel, with the card's summary and its result files.
- `notify+wake`: the notice, and the subscribed Profile also takes a turn to act on it.

A notice shows only the card's title and the first line of its summary, cut at 200 characters. The card's result isn't posted. Files reach the channel only as uploads: each path in `kanban_complete`'s `artifacts`, or a file path named in the summary or result. So each worker's SOUL.md tells it to write its full output to a markdown file and list it in `artifacts`. Without that, the researcher once put its whole deliverable in `metadata`, and Discord got a cut-short line.

`/kanban create` always subscribes with `notify+wake`, and cards copy their parent's and creator's subscriptions, so cards the orchestrator adds mid-run get it too. Waking is wrong here: it wakes the default Profile, which has no kanban tools in Discord and digs through `kanban.db` by hand instead of posting the result.

So every Discord subscription is kept on plain `notify`. The [`hermes-kanban-notices`](../../../ansible/services/tasks/hermes-kanban-notices.yaml) post-task, on each Deploy:

- switches any Discord subscription that isn't `notify` to `notify`;
- adds two SQLite triggers on the subscription table, which switch every new or changed Discord subscription to `notify` the moment it's written. A Deploy re-adds a missing trigger, for example after an upgrade rebuilt the table.

Before the gateway first creates `kanban.db`, the task does nothing; the next Deploy adds the triggers.

Confusing part: the triggers depend on `kanban.db`'s schema, which an image Version Bump can change. They are a shortcut until Hermes has a setting for notify-only subscriptions.

## What a Deploy does to running cards

A Deploy recreates the container, which kills every running worker. What happens next depends on the container's hostname:

- Each card's claim records the hostname of the worker that took it, and the dispatcher reclaims dead workers only for its own hostname.
- Docker's default hostname is the container ID, which changes on every recreate. So after a Deploy, the new dispatcher saw the old claims as another host's and left the cards until their 15-minute claim expired.
- `hostname: hermes` in `hermes.yaml` keeps the name fixed. The dispatcher sees the dead claims as its own and requeues those cards on its next tick.

A requeued card reruns from the start, with no manual step, and the kill counts as a failure toward the card's retry limit. So before a Deploy, check for running cards first ([running.md](running.md)).
