# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase. This is a single-context repo.

## Before exploring, read these

The glossary (`CONTEXT.md`, this repo's name for `GLOSSARY.md`), the ADRs and the specs live outside the repo, where your user-level instructions put agent files.

- **Glossary**: read it before naming anything.
- **ADRs**: read the ones that touch the area you're about to work in.

`docs/` describes the current state and the specs are design history; where they disagree with the code, the code and `docs/` win.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as the glossary defines it. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0003 (OPNsense bare metal with Ansible), but worth reopening because…_
