terraform_dir := justfile_directory() / "terraform"

# Run terraform apply for a stack, e.g. `just tf::apply cloudflare`
apply stack *args:
    bws run -- terraform -chdir={{ terraform_dir }}/{{ stack }} apply {{ args }}
