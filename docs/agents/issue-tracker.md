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
