#!/usr/bin/env bash
# post-checkout hook: a worktree git just created has no .env and no Ansible collections.
# Never fails: a non-zero exit fails `git worktree add`, and the agent-manager spawn behind it.
set -uo pipefail

# git passes a null old ref only when it creates the checkout (a new worktree or a clone).
[[ ${PRE_COMMIT_FROM_REF:-} =~ ^0+$ ]] || exit 0

main=$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")
[[ $main == "$(git rev-parse --show-toplevel)" ]] && exit 0

[[ -e .env || ! -e $main/.env ]] || ln -s "$main/.env" .env
# Seeding from the main checkout turns a ~30s download into a ~1s check; the install still fixes a changed pin.
[[ -e .cache/ansible/collections || ! -d $main/.cache/ansible/collections ]] ||
  { mkdir -p .cache/ansible && cp -a "$main/.cache/ansible/collections" .cache/ansible/; }
ansible-galaxy collection install -r requirements.yml -p .cache/ansible/collections >/dev/null ||
  echo "worktree-setup: run 'ansible-galaxy collection install -r requirements.yml' by hand" >&2
exit 0
