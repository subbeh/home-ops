---
covers:
  - ansible/services/hermes.yaml
  - ansible/services/tasks/hermes-vault-history.yaml
---
# The vault

The vault is a folder of plain markdown notes that you and Hermes both read and write. You open it on the laptop (in Obsidian or any editor), and Hermes keeps its notes there through the bundled `llm-wiki` skill. An hourly git history, committed on the vps and synced with the notes, records every change, so any edit Hermes makes can be reviewed and undone.

## Where it lives

```text
 laptop                         vps
 /data/workspace/vault ─ syncthing ─ /opt/workspace/vault ── mounted rw ── /vault (hermes container)
   └─ .git (read only here)            └─ .git ◄── hourly commit (host cron, as apps)
```

- **Laptop**: `/data/workspace/vault`. Syncthing already syncs all of `/data/workspace`, so nothing extra is set up for the vault.
- **vps**: `/opt/workspace/vault` (`services_workspace_dir`), owned by `apps`. The hermes Deploy creates it before mounting it, so Docker never creates it as root.
- **Container**: `/vault`, mounted read-write from the vps path, never from syncthing's data dir.
- **Ownership**: syncthing on the vps writes as `apps` (2000), and hermes runs as the same uid, so each can edit what the other created. Files Hermes creates reach the laptop with their permission bits, owned by your user there.

## Which Profiles use it

The `vault` Key set ([keys.md](keys.md)) puts `WIKI_PATH=/vault` in the `.env` of default and the Kanban Profiles (orchestrator, researcher, writer, reviewer). `llm-wiki` reads it to find the vault. The set also adds `/vault` to `HERMES_WRITE_SAFE_ROOT`: the image sets it to `/opt/data`, and `write_file` and `patch` refuse any path outside it. ops gets neither. The container's filesystem is shared, though, so ops could still reach `/vault`: keeping it off is a matter of instruction, not enforcement ([safety.md](safety.md#what-one-profile-can-see-of-another)).

The `health/` folder holds your medical records, such as blood-test results, for the health Profile ([profiles.md](profiles.md#the-health-profile)). health gets no `vault` set, so its file tools read the records but can't change them, and its terminal starts in `/vault/health`. The folder is private by instruction only: the `SOUL.md` of default and of each Kanban Profile tells it to stay out, but one container and one shared mount mean any Profile could read it. Like every note, the records sync to the laptop, land in the vault's git history and go to the model provider whenever health reads them.

## Hermes's own notes

`SCHEMA.md` at the vault's root is the contract for every note: the folder layout, frontmatter, tags, links and who writes where. You approved it, and you change it in Obsidian like any note. On top of `llm-wiki`'s folders, default keeps a layer for continuity:

| Note | Written by | What it holds |
|---|---|---|
| `daily/YYYY-MM-DD.md` | the nightly pass | One day's sessions: topics, decisions, open threads |
| `weekly/YYYY-Www.md` | the weekly pass | The ISO week's themes and standing decisions, each linking its daily notes, plus a memory check |
| `now.md` | the nightly pass | Current focus, open threads, the last three days and what's due soon: at most 40 short lines |
| `watching.md` | the nightly pass, plan-day, wrap-up | Open loops ("waiting on X", "I'll look at Y"), one line each, deleted once closed |
| `notified/YYYY-MM.md` | plan-day, wrap-up, morning-brief | One line per item raised: what, why now, from where |
| `entities/`, `concepts/` | both passes | A note per subject once it shows up in two daily notes |

**The passes**: the `vault-notes` skill, run by two default cron jobs ([profiles.md](profiles.md#cron-jobs)). The nightly one reads yesterday's sessions through `session_search`; the weekly one, early Monday, reads the week's daily notes. Both may use only the file tools and `session_search`, and deliver nowhere, so a run messages nobody unless it fails.

**Session start**: default's `terminal.cwd` is `/vault`, and the vault holds `.hermes.md`, a symlink to `now.md`. Hermes loads the `.hermes.md` it finds from its working directory into every session's system prompt, with the frontmatter stripped, so a fresh Discord chat knows yesterday's open threads without a tool call. Cron runs load no context files unless the job sets a `workdir`, so plan-day and wrap-up read `now.md` themselves. Side effect: default's terminal commands start in the vault.

**Open loops and the ledger**: plan-day and wrap-up bring up `watching.md` items whose recheck date has come, or that the day's talk touched, and skip any the ledger shows they already raised unless it changed since. The Friday wrap-up reads the week's ledger lines and proposes cuts; a cut gets a `cut:` line, so it doesn't come back. The morning brief skips stories already in the ledger. None of them messages you outside its own run.

**Memory entries**: MEMORY.md and USER.md entries start `[YYYY-MM-DD] [CATEGORY] -` (the date last verified) or `[PERMANENT] [CATEGORY] -`, and procedures go into skills. The weekly pass lists stale, conflicting or duplicate entries in its note and adds one `watching.md` line, so plan-day raises the review once. It never edits memory itself.

## What the Kanban team writes

A Kanban goal's output goes to `research/`, so it outlives the board ([kanban.md](kanban.md)). The rules are in each Profile's `SOUL.md`:

- **The folder**: each goal gets one, `research/YYYY-MM-DD-<slug>/` (the date it starts and a short slug). The first cards come from Hermes's auto-decomposer, whose prompt is fixed, so they name no folder. A worker uses the folder named on its card, else the one a parent card's or its own recent card's artifacts are in for the same goal, else creates one.
- **orchestrator**: names the folder on every card it adds, fix cards included. Its closing summary gives the deliverable's path.
- **researcher**: writes its notes there as `notes-<topic>.md`.
- **writer**: writes the deliverable there as `<slug>.md`, and adds one line for it under `## Research` in `index.md`. A fix card overwrites the same file, and the hourly history keeps the earlier draft.
- **reviewer**: never writes to the vault. Its report goes to Discord only.

Notes and deliverables start with YAML frontmatter: `title`, `date`, `card` (the card id) and `sources` (every URL cited). The worker lists the file's vault path in `kanban_complete`'s `artifacts`, and Discord uploads it from there.

Researcher and writer write only inside their goal's folder, plus the writer's `index.md` line: never in `raw/`, `entities/` or another folder the `llm-wiki` skill uses, and never in another goal's folder. That is by instruction only: the shared filesystem doesn't enforce it.

Confusing part: whether a recent card belongs to the same goal is the model's call, so two research cards on one goal can end up in two folders. In the first test goal, the second researcher found the first one's folder from its recent work.

## History and rollback

The [`hermes-vault-history`](../../../ansible/services/tasks/hermes-vault-history.yaml) post-task makes the vault an ordinary git repo, with `.git` inside it. Syncthing syncs `.git` with the notes, so the history reads the same on the laptop as on the vps.

- **When**: a host cron job, run as `apps` at :50 each hour, commits whatever changed, with an empty message. An hour with no change commits nothing. Restic's backup on the hour picks the repo up, so nothing is ever pushed.
- **One committer**: that cron job is the only thing that writes to `.git`. Read the history anywhere, but never commit, check out or otherwise run a writing git command on the laptop (see [Risks](#risks)). `git status` counts: it rewrites the index.
- **Left out**: syncthing's in-flight transfer files and `.stversions/`. Syncthing conflict copies (`*.sync-conflict-*`) stay in, so they show up in the history.

Reading, on either side from the vault (on the vps, prefix `sudo -u apps`):

```sh
git log --format='%h %ci' --stat     # which hours changed what
git log -p -- <note>.md              # one note's earlier versions
```

To roll a note back, restore it on the vps, so the one committer's side writes it:

```sh
sudo -u apps git checkout <commit> -- <note>.md   # from /opt/workspace/vault
```

A restore writes into the live vault, and syncthing carries it to the laptop. The next hourly run commits the rollback as a new snapshot, so the history only ever grows. On the laptop, copy the old version out with `git show <commit>:<note>.md` instead.

## Risks

- **Hermes can rewrite the history**: `.git` sits inside the read-write mount, so Hermes can change or delete it. The restic backups are the copy it can't reach. Accepted, so the history reads on the laptop.
- **A synced `.git` can corrupt**: syncthing doesn't know git's files belong together, so git writing on both sides at once can leave a broken repo. Commit only through the vps cron job, never from the laptop.
- **Injected text**: the Kanban Profiles read the web, and what they write into the vault can carry injected instructions that default reads later. The history is the rollback.
- **`now.md` in every prompt**: Hermes loads it as project context, a tier it is told to follow. The nightly pass writes it from sessions that may quote web text, so `SCHEMA.md`, the skill and `now.md`'s first line all say notes are data, not instructions. That is by instruction only.
- **Conflicts**: when you and Hermes edit the same note at once, syncthing keeps both, as a `.sync-conflict` copy.
- **Model providers**: whatever Hermes reads from the vault is sent to OpenCode Go's model providers.
