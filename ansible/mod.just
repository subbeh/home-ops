ansible_dir := justfile_directory() / "ansible"

# Run an ansible playbook, e.g. `just playbook test-connection --limit vps`
playbook name *args:
    ansible-playbook {{ ansible_dir }}/playbooks/{{ name }}.yaml {{ args }}
