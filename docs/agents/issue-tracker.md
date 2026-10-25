# Issue tracker: aven

Issues and specs for this repo live as tasks in aven, a local-first task manager synced over the tailnet, in project `home-ops` (refs `HO-*`). They stay off GitHub because the repo is public. Run `aven skill` for the full primer.

## Conventions

- **Create an issue**: `aven add --project home-ops "<title>" --description-stdin <<'EOF' ... EOF`. Capture the ref it prints.
- **Read an issue**: `aven context <ref>` (description, labels, relations, recent notes).
- **List issues**: `aven list --open --project home-ops`, with `--label`, `--status` or `--ready` filters. `aven search --project home-ops "<words>"` also finds done and canceled tasks.
- **Make an issue a child of a parent**: mark the parent with `aven edit <parent> --epic on`, then `aven epic add <child> <parent>`.
- **Comment on an issue**: `aven note <ref> --stdin <<'EOF' ... EOF`
- **Apply / remove labels**: `aven edit <ref> --label "..."` / `--remove-label "..."`
- **Close**: add a note, then `aven edit <ref> --status done` (or `--status canceled` when it won't be done).

Task refs are local: keep them out of commit messages, PR descriptions and GitHub. A merged PR doesn't close its task; close it by hand.

## Organisation

- **Titles** are Conventional Commits subjects with the repo's scopes (`feat(opnsense): ...`, `chore(terraform): ...`), so a done task's title can become its commit message.
- **Status** follows the work: `inbox` (not triaged yet) → `backlog` (accepted, not scheduled) → `todo` (next up) → `active` (in progress) → `done` or `canceled`. An epic is `active` while any of its children is.
- **Triage label**: every open task carries exactly one label from [triage-labels.md](triage-labels.md). A `needs-info` task lists its open questions in a note.
- **Priority** follows the critical path. `high`: the blockers of the active epic and the work on its path. `medium`: the rest of that epic. `low`: backlog and standalone tasks. `urgent` is for something broken.
- **Epics** group linked work by theme, and they nest. Network work lives under the *network architecture* epic, and a large effort gets a nested epic with its spec in the description (for example the OPNsense bring-up). Unrelated one-off tasks stay outside any epic: don't create an epic for a single task.
- **Dependencies, epics and related links** each do one job. `aven dep add` sets execution order, and `aven list --ready` hides blocked tasks. Epic membership only groups and never blocks. `aven related add` links context, with no order.
- **Handover**: when you stop mid-task, leave a note with Done, State, Next and Open, so the next session can pick it up from `aven context` alone.

Useful views: `aven list --ready` (what to do next), `aven epic list <epic>` (an epic's progress), `aven list --open --label needs-info` (what's waiting on answers), `aven list --blocked`.

## Pull requests as a triage surface

**PRs as a request surface: no.** Triage runs on aven tasks only.

## When a skill says "publish to the issue tracker"

Create an aven task in project `home-ops`.

## When a skill says "fetch the relevant ticket"

Read it as in **Read an issue** above.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single epic task with **child** tasks as tickets.

- **Map**: an epic labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog in its description. `aven add --project home-ops --epic --label wayfinder:map "<title>"`.
- **Child ticket**: a task added to the map with `aven epic add <child> <map>`. Labels: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`).
- **Blocking**: `aven dep add <blocked> <blocker>`. A ticket is unblocked when every blocker is done or canceled.
- **Frontier query**: `aven epic list <map>`, keep the open children that `aven list --ready --project home-ops` also shows and that aren't `active`; first in map order wins.
- **Claim**: `aven edit <ref> --status active`, the session's first write.
- **Resolve**: `aven note <ref> --stdin` with the answer, then `aven edit <ref> --status done`, then append a context pointer (gist + ref) to the map's Decisions-so-far with `aven text get` / `aven text set --if-sha256`.
