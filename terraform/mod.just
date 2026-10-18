terraform_dir := justfile_directory() / "terraform"

# Apply a locally executed stack, e.g. `just tf::apply tfe-admin`; the others apply in TFC on merge
[script]
apply stack *args:
    export BW_ACCESS_TOKEN="$BWS_ACCESS_TOKEN"
    export BW_ORGANIZATION_ID="$(bws project list | jq -r '.[0].organizationId')"
    export GITHUB_TOKEN="$(gh auth token)"
    terraform -chdir={{ terraform_dir }}/{{ stack }} apply {{ args }}
