# Project (short name)
project         = "gp"

# Project (long name)
project_long    = "the-golden-project"

# AWS primary region
region_primary  = "us-east-1"

# AWS Region for DR replication (required by the backend but also used for other resources)
region_secondary      = "us-west-2"

# Account IDs
management_account_id = "XXXXXXXXXXXX"
security_account_id = "XXXXXXXXXXXX"
shared_account_id = "XXXXXXXXXXXX"

# Accounts
accounts    = {
  management = {
      email = "aws+management@example.com"
  }
  security = {
      email = "aws+security@example.com"
  }
  shared = {
      email = "aws+shared@example.com"
  }
}

# AWS SSO
sso_enabled   = false
sso_start_url = "https://bbleverage.awsapps.com/start"
sso_region    = "us-east-1"