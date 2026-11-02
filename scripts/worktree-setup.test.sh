#!/usr/bin/env bash
# Self-test for worktree-setup.sh against a throwaway repo; run with `just docs-test`.
set -euo pipefail

setup=$(cd "$(dirname "$0")" && pwd)/worktree-setup.sh
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# A stub ansible-galaxy that logs its args, and fails when asked to.
mkdir "$tmp/bin"
# shellcheck disable=SC2016 # the stub expands $* itself
printf '#!/bin/sh\necho "$*" >>"%s/galaxy.log"\n[ -z "${GALAXY_FAIL:-}" ]\n' "$tmp" >"$tmp/bin/ansible-galaxy"
chmod +x "$tmp/bin/ansible-galaxy"
export PATH=$tmp/bin:$PATH

git init -q "$tmp/main"
git -C "$tmp/main" -c user.email=t@example.com -c user.name=t commit -q --allow-empty -m init
echo TOKEN=x >"$tmp/main/.env"
mkdir -p "$tmp/main/.cache/ansible/collections/ansible_collections"
git -C "$tmp/main" worktree add -q "$tmp/wt" -b wt
null=0000000000000000000000000000000000000000

# A branch switch in a worktree does nothing.
(cd "$tmp/wt" && PRE_COMMIT_FROM_REF=abc123 "$setup")
[[ ! -e $tmp/wt/.env && ! -e $tmp/galaxy.log ]]

# The main checkout does nothing.
(cd "$tmp/main" && PRE_COMMIT_FROM_REF=$null "$setup")
[[ ! -e $tmp/galaxy.log ]]

# A new worktree links .env and installs the collections into its own cache.
(cd "$tmp/wt" && PRE_COMMIT_FROM_REF=$null "$setup")
[[ $(readlink "$tmp/wt/.env") == "$tmp/main/.env" ]]
[[ -d $tmp/wt/.cache/ansible/collections/ansible_collections ]]
grep -qx 'collection install -r requirements.yml -p .cache/ansible/collections' "$tmp/galaxy.log"

# A failed install still exits 0, so `git worktree add` succeeds.
(cd "$tmp/wt" && GALAXY_FAIL=1 PRE_COMMIT_FROM_REF=$null "$setup" 2>/dev/null)

echo "worktree-setup: ok"
