terraform {
  backend "s3" {
    bucket       = "kiwi-tfstate-289981265147"
    key          = "kiwi/terraform.tfstate"
    region       = "eu-north-1"
    encrypt      = true
    use_lockfile = true
  }

  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.73"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.5"
    }
  }
}
