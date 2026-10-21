# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase. This is a single-context repo.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root: the glossary (this repo's name for `GLOSSARY.md`).
- **`docs/adr/`**: read ADRs that touch the area you're about to work in.

`docs/` describes the current state and `.specs/` is design history; where they disagree with the code, the code and `docs/` win.

## File structure

```
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-auto-deploy-via-semaphore-over-tailscale.md
│   └── 0002-network-file-is-the-source.md
├── ansible/
└── terraform/
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0003 (OPNsense bare metal with Ansible), but worth reopening because…_
