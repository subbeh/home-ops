---
name: update-docs
description: Bring covering docs in line with a code change. Use when the docs-covers hook fails, or before committing changes to code that a doc's covers: frontmatter matches.
covers:
  - scripts/docs-covers.sh
  - .pre-commit-config.yaml
---
# Update docs

Hand-written docs, `CLAUDE.md` and the skills each list the code they describe in `covers:` frontmatter. A commit that changes covered code must stage every covering doc, or carry `Docs: none (<reason>)`. [docs/README.md](../../../docs/README.md) has the rules.

## Steps

1. **List** the docs to check. Take them from the hook output, or stage the change and run:
   `printf 'x\n' > /tmp/docs-msg && scripts/docs-covers.sh /tmp/docs-msg`
   Done when you have every doc it names.
2. **Compare**: for each doc, read the whole doc and the staged diff of the files it covers (`git diff --cached -- <files>`). Done when every statement in the doc that touches the changed files is marked true, false or incomplete.
3. **Edit** only the false and incomplete statements, in the doc's existing voice and terse style, with no versions. Stage each edited doc.
4. **No edit needed**: when every statement still holds, propose a trailer that names the reason, e.g. `Docs: none (comment-only change in restic.yaml)`.
5. **Generated pages**: when the sources of generated pages changed (inventory, Service files, the network files in `ansible/group_vars/all`, Terraform stacks), run `just docs` and stage the result. Generated pages change only through `just docs`.
6. **Re-check**: run the command from step 1 again. Done when it exits 0, or when only docs covered by the proposed trailer remain.

## Gotchas

- **Too many docs flagged**: when one doc keeps getting flagged for unrelated changes, narrow its `covers:` globs. Keep the rule itself as it is.
- **New docs**: a new hand-written doc needs `covers:` frontmatter and a row in docs/README.md.
