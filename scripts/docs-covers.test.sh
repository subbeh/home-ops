#!/usr/bin/env bash
# Self-test for docs-covers.sh against a throwaway repo; run with `just docs-test`.
set -euo pipefail

check=$(cd "$(dirname "$0")" && pwd)/docs-covers.sh
repo=$(mktemp -d)
trap 'rm -rf "$repo"' EXIT
cd "$repo"
git init -q
git config user.email test@example.com
git config user.name test

mkdir -p docs ansible/roles .claude/skills/add-service
printf -- '---\ncovers:\n  - ansible/roles/**\n  - "ansible/inventory.yml"\n---\n# A\n' > docs/a.md
printf -- '---\nname: add-service\ncovers:\n  - ansible/roles/**\ndescription: x\n---\n' > .claude/skills/add-service/SKILL.md
printf -- '# no frontmatter\n' > docs/b.md
touch ansible/roles/main.yaml ansible/inventory.yml README.md
git add -A && git commit -qm init

fails=0
# expect <0|1> <description> <message>: runs the check on what's staged now.
expect() {
  printf '%s\n' "$3" > msg
  if "$check" msg 2>/dev/null; then got=0; else got=1; fi
  if [ "$got" = "$1" ]; then echo "ok:   $2"; else echo "FAIL: $2 (exit $got, want $1)"; fails=1; fi
}
stage() { git reset -q; for f in "$@"; do echo x >> "$f"; git add "$f"; done; }

stage README.md;                                   expect 0 "uncovered change passes" "chore: x"
stage ansible/inventory.yml;                       expect 1 "covered change without doc fails" "feat: x"
stage ansible/inventory.yml docs/a.md;             expect 0 "covered change with doc passes" "feat: x"
stage ansible/roles/main.yaml docs/a.md;           expect 1 "every covering doc is required" "feat: x"
stage ansible/roles/main.yaml docs/a.md .claude/skills/add-service/SKILL.md
                                                   expect 0 "all covering docs staged passes" "feat: x"
stage ansible/roles/main.yaml;                     expect 0 "trailer bypasses" $'feat: x\n\nDocs: none (comment typo)'
stage ansible/roles/main.yaml;                     expect 1 "empty trailer reason fails" $'feat: x\n\nDocs: none ( )'
stage ansible/roles/main.yaml;                     expect 1 "commented-out trailer fails" $'feat: x\n# Docs: none (x)'
git rev-parse HEAD > .git/MERGE_HEAD;              expect 0 "merge commit passes" "Merge x"
rm .git/MERGE_HEAD

exit "$fails"
