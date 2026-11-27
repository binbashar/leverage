#=============================#
# AWS Provider Settings       #
#=============================#
provider "aws" {
  region  = var.region
  profile = var.profile
}

#=============================#
# Backend Config (partial)    #
#=============================#
terraform {
  required_version = "~> 1.2"

  required_providers {
    aws = "~> 4.40"
  }

  backend "s3" {
    key = "management/sso/terraform.tfstate"
  }
}

#------------------------------------------------------------------------------
# Important: this data source will only work after SSO has been activated
#------------------------------------------------------------------------------
data "aws_ssoadmin_instances" "main" {}
