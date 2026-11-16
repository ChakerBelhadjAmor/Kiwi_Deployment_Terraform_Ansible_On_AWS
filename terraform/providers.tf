# Credentials are never configured here: use `aws sso login` / AWS_PROFILE.
provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project = var.project_tag
      Expires = var.expires_tag
    }
  }
}
