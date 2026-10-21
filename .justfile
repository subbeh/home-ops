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

# Install the git hooks and Ansible collections, once per clone
[group('docs')]
setup:
    pre-commit install
    ansible-galaxy collection install -r {{ justfile_directory() }}/requirements.yml

# Regenerate the generated pages in docs/
[group('docs')]
docs:
    ansible-playbook {{ justfile_directory() }}/ansible/playbooks/docs.yaml

# Run the PR check's Ansible steps as CI does, without the mise env
[group('docs')]
check:
    # The mise shim re-adds ANSIBLE_PLAYBOOK_DIR, which moves relative include_vars paths; call the real binaries.
    bin=$(dirname "$(mise which ansible)")
    cd {{ justfile_directory() }}
    ci() { env -u ANSIBLE_PLAYBOOK_DIR ANSIBLE_CONFIG=ansible/ansible.cfg "$bin/$@"; }
    ci ansible-playbook --syntax-check ansible/playbooks/services.yaml
    # Its success output is every Service definition, so print it only on failure.
    out=$(ci ansible localhost -m ansible.builtin.include_vars \
      -a '{"dir": "ansible/services", "files_matching": "\\.ya?ml$", "depth": 1}' 2>&1) || { echo "$out"; exit 1; }

# Self-test the docs-covers commit-msg hook
[group('docs')]
docs-test:
    {{ justfile_directory() }}/scripts/docs-covers.test.sh
