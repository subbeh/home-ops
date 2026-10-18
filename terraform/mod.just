terraform_dir := justfile_directory() / "terraform"

# Initialize a stack against Terraform Cloud, e.g. `just tf::init tfe-admin`
[script]
init stack *args:
    export TF_TOKEN_app_terraform_io="$(bws secret list -o json | jq -r '.[] | select(.key == "TFC_API_TOKEN").value')"
    terraform -chdir={{ terraform_dir }}/{{ stack }} init {{ args }}

# Apply a locally executed stack, e.g. `just tf::apply tfe-admin`; the others apply in TFC on merge
[script]
apply stack *args:
    secrets="$(bws secret list -o json)"
    secret() { jq -r --arg k "$1" '.[] | select(.key == $k).value' <<< "$secrets"; }
    # TFC: the cloud block reads TF_TOKEN_app_terraform_io, the tfe provider TFE_TOKEN.
    export TF_TOKEN_app_terraform_io="$(secret TFC_API_TOKEN)"
    export TFE_TOKEN="$TF_TOKEN_app_terraform_io"
    export BW_ACCESS_TOKEN="$BWS_ACCESS_TOKEN"
    export BW_ORGANIZATION_ID="$(jq -r '.[0].organizationId' <<< "$(bws project list -o json)")"
    export GITHUB_TOKEN="$(gh auth token)"
    terraform -chdir={{ terraform_dir }}/{{ stack }} apply {{ args }}
