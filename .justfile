#!/usr/bin/env -S just --justfile

set default-list
set default-script
set lazy
set quiet
set script-interpreter := ['bash', '-euo', 'pipefail']
set shell := ['bash', '-euo', 'pipefail', '-c']

# Ansible Recipes
[group('ansible')]
mod ansible "ansible"

# Terraform Recipes
[group('tf')]
mod tf "terraform"

[private]
log lvl msg *args:
    gum log -t rfc3339 -s -l "{{ lvl }}" "{{ msg }}" {{ args }}

# Install the git hooks, once per clone
[group('docs')]
setup:
    pre-commit install

# Regenerate the generated pages in docs/
[group('docs')]
docs:
    ansible-playbook {{ justfile_directory() }}/ansible/playbooks/docs.yaml

# Self-test the docs-covers commit-msg hook
[group('docs')]
docs-test:
    {{ justfile_directory() }}/scripts/docs-covers.test.sh
