ansible_dir := justfile_directory() / "ansible"

# Run an ansible playbook, e.g. `just playbook test-connection --limit vps`
[script]
playbook name *args:
    # A real run from a tree that isn't main can silently undo what main last deployed;
    # --check runs stay open so worktrees can preview.
    case " {{ args }} " in
      *" --check "* | *" -C "*) ;;
      *)
        if [ -z "${DEPLOY_FROM_BRANCH:-}" ]; then
          cd {{ justfile_directory() }}
          reason=""
          [ -n "$(git status --porcelain)" ] && reason="the working tree has uncommitted changes"
          [ "$(git rev-parse HEAD)" = "$(git rev-parse main)" ] || reason="HEAD is not local main"
          if [ -n "$reason" ]; then
            echo "Refusing a real run: $reason. Land on main and run from there, or set DEPLOY_FROM_BRANCH=1 to override." >&2
            exit 1
          fi
        fi
        ;;
    esac
    ansible-playbook {{ ansible_dir }}/playbooks/{{ name }}.yaml {{ args }}
