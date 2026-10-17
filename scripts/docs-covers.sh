#!/usr/bin/env bash
# commit-msg hook: every doc whose `covers:` frontmatter matches a staged file must be staged
# too, unless the message has a `Docs: none (<reason>)` trailer. Usage: docs-covers.sh <msg-file>
set -euo pipefail

msg_file=$1

git rev-parse -q --verify MERGE_HEAD >/dev/null && exit 0
grep -qE '^Docs: none \([^)]*[^) ][^)]*\)' "$msg_file" && exit 0

# The `covers:` list of a doc's frontmatter, one glob per line.
covers() {
  awk 'NR == 1 && $0 != "---" { exit }
       NR > 1 && $0 == "---" { exit }
       /^covers:/ { c = 1; next }
       c && /^[[:space:]]*- / { sub(/^[[:space:]]*- /, ""); gsub(/["\047]/, ""); print; next }
       c && /^[^[:space:]]/ { c = 0 }' "$1"
}

staged=$(git diff --cached --name-only --no-renames)
[ -n "$staged" ] || exit 0

missing=""
while IFS= read -r doc; do
  [ -f "$doc" ] || continue
  grep -qxF "$doc" <<< "$staged" && continue
  while IFS= read -r glob; do
    [ -n "$glob" ] || continue
    while IFS= read -r file; do
      # Unquoted on purpose: a glob, where * also matches /.
      # shellcheck disable=SC2053
      if [[ $file == $glob ]]; then
        missing+="  $doc (covers: $glob, changed: $file)"$'\n'
        continue 3
      fi
    done <<< "$staged"
  done < <(covers "$doc")
done < <(git ls-files -- 'docs/*.md' CLAUDE.md '.claude/skills/*/SKILL.md')

[ -z "$missing" ] && exit 0

cat >&2 <<EOF
These docs cover staged changes but aren't staged themselves:
${missing}
Update them in this commit (the update-docs skill helps), or add a trailer to the
commit message saying why none is needed:  Docs: none (<reason>)
EOF
exit 1
