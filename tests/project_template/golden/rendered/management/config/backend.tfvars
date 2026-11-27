#
# Backend Configuration
#

# AWS Profile (required by the backend but also used for other resources)
profile         = "gp-bootstrap"

# S3 bucket
bucket          = "gp-management-terraform-backend"

# AWS Region (required by the backend but also used for other resources)
region          = "us-east-1"

# Enable DynamoDB server-side encryption?
encrypt         = true

# DynamoDB Table Name
dynamodb_table  = "gp-management-terraform-backend"