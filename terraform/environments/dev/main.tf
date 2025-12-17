locals {
  environment = "dev"
  aws_region  = "eu-west-1"

  tags = {
    Project     = "APIM"
    Environment = local.environment
    ManagedBy   = "Terraform"
    CostCenter  = "Platform"
  }
}

# VPC Module
module "vpc" {
  source = "../../modules/vpc"

  vpc_cidr           = "10.0.0.0/16"
  availability_zones = ["eu-west-1a", "eu-west-1b"]
  environment        = local.environment
  project_name       = "apim"
  aws_region         = local.aws_region
  tags               = local.tags
}

# IAM Module
module "iam" {
  source = "../../modules/iam"

  environment  = local.environment
  project_name = "apim"
  tags         = local.tags
}

# S3 Buckets
resource "aws_s3_bucket" "artifacts" {
  bucket = "apim-artifacts-${local.environment}"

  tags = merge(
    local.tags,
    {
      Name = "APIM Artifacts"
    }
  )
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket" "backups" {
  bucket = "apim-backups-${local.environment}"

  tags = merge(
    local.tags,
    {
      Name = "APIM Backups"
    }
  )
}

resource "aws_s3_bucket_versioning" "backups" {
  bucket = aws_s3_bucket.backups.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id

  rule {
    id     = "archive-old-backups"
    status = "Enabled"

    transition {
      days          = 30
      storage_class = "GLACIER"
    }

    expiration {
      days = 90
    }
  }
}

resource "aws_s3_bucket" "vault_storage" {
  bucket = "apim-vault-storage-${local.environment}"

  tags = merge(
    local.tags,
    {
      Name = "Vault Storage Backend"
    }
  )
}

resource "aws_s3_bucket_versioning" "vault_storage" {
  bucket = aws_s3_bucket.vault_storage.id

  versioning_configuration {
    status = "Enabled"
  }
}

# KMS Key for Vault Auto-Unseal
resource "aws_kms_key" "vault" {
  description             = "KMS key for Vault auto-unseal"
  deletion_window_in_days = 10

  tags = merge(
    local.tags,
    {
      Name = "vault-unseal-key"
    }
  )
}

resource "aws_kms_alias" "vault" {
  name          = "alias/apim-vault-${local.environment}"
  target_key_id = aws_kms_key.vault.key_id
}

# Security Groups
resource "aws_security_group" "alb" {
  name        = "apim-alb-sg-${local.environment}"
  description = "Security group for Application Load Balancer"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTPS from internet"
  }

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTP from internet (redirect to HTTPS)"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    local.tags,
    {
      Name = "apim-alb-sg"
    }
  )
}

resource "aws_security_group" "webmethods" {
  name        = "apim-webmethods-sg-${local.environment}"
  description = "Security group for webMethods Gateway"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port       = 9072
    to_port         = 9072
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
    description     = "webMethods UI from ALB"
  }

  ingress {
    from_port   = 5555
    to_port     = 5555
    protocol    = "tcp"
    cidr_blocks = [module.vpc.vpc_cidr]
    description = "webMethods Runtime from VPC"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    local.tags,
    {
      Name = "apim-webmethods-sg"
    }
  )
}

resource "aws_security_group" "portal" {
  name        = "apim-portal-sg-${local.environment}"
  description = "Security group for Developer Portal"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port       = 18101
    to_port         = 18101
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
    description     = "Portal HTTPS from ALB"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    local.tags,
    {
      Name = "apim-portal-sg"
    }
  )
}

resource "aws_security_group" "jenkins" {
  name        = "apim-jenkins-sg-${local.environment}"
  description = "Security group for Jenkins"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port       = 8080
    to_port         = 8080
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
    description     = "Jenkins from ALB"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    local.tags,
    {
      Name = "apim-jenkins-sg"
    }
  )
}

resource "aws_security_group" "vault" {
  name        = "apim-vault-sg-${local.environment}"
  description = "Security group for Vault"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port   = 8200
    to_port     = 8200
    protocol    = "tcp"
    cidr_blocks = [module.vpc.vpc_cidr]
    description = "Vault API from VPC"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    local.tags,
    {
      Name = "apim-vault-sg"
    }
  )
}

# Output key values
output "vpc_id" {
  value = module.vpc.vpc_id
}

output "private_subnet_ids" {
  value = module.vpc.private_subnet_ids
}

output "kms_key_id" {
  value = aws_kms_key.vault.id
}
