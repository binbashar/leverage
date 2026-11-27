#=============================#
# AWS Provider Settings       #
#=============================#
provider "aws" {
  region  = var.region
  profile = var.profile
}

provider "aws" {
  alias   = "main_region"
  region  = var.region
  profile = var.profile
}

provider "aws" {
  alias   = "secondary_region"
  region  = var.region_secondary
  profile = var.profile
}

terraform {
  required_version = "~> 1.2"

  required_providers {
    aws = "~> 5.0"
  }

  # Uncomment after first `apply`
  # backend "s3" {
  #   key = "management/tf-backend/terraform.tfstate"
  # }
}
