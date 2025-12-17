terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket         = "apim-terraform-state-dev"
    key            = "apim/terraform.tfstate"
    region         = "eu-west-1"
    encrypt        = true
    dynamodb_table = "apim-terraform-locks"

    # Uncomment after creating the S3 bucket and DynamoDB table manually first
    # See bootstrap instructions in docs/SETUP.md
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "APIM"
      ManagedBy   = "Terraform"
      Environment = var.environment
    }
  }
}
