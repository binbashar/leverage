locals {
  organizational_units = {
    security = {
      policy = aws_organizations_policy.default
    },
    shared = {
      policy = aws_organizations_policy.standard
    }
  }

  management_account = {
    email = "aws+management@example.com"
  }

  accounts = {
    security = {
      email     = "aws+security@example.com",
      parent_ou = "security"
    },
    shared = {
      email     = "aws+shared@example.com",
      parent_ou = "shared"
    }
  }
}