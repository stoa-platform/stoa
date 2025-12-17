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

    filter {}

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

# EC2 Instances Module
module "ec2" {
  source = "../../modules/ec2"

  environment  = local.environment
  project_name = "apim"
  vpc_id       = module.vpc.vpc_id

  private_subnet_ids = module.vpc.private_subnet_ids

  webmethods_instance_type = var.webmethods_instance_type
  portal_instance_type     = var.portal_instance_type
  jenkins_instance_type    = var.jenkins_instance_type
  vault_instance_type      = var.vault_instance_type

  webmethods_security_group_id = aws_security_group.webmethods.id
  portal_security_group_id     = aws_security_group.portal.id
  jenkins_security_group_id    = aws_security_group.jenkins.id
  vault_security_group_id      = aws_security_group.vault.id

  webmethods_instance_profile = module.iam.webmethods_instance_profile
  portal_instance_profile     = module.iam.portal_instance_profile
  jenkins_instance_profile    = module.iam.jenkins_instance_profile
  vault_instance_profile      = module.iam.vault_instance_profile

  kms_key_id       = aws_kms_key.vault.id
  vault_bucket     = aws_s3_bucket.vault_storage.bucket
  artifacts_bucket = aws_s3_bucket.artifacts.bucket

  tags = local.tags
}

# Application Load Balancer Module
module "alb" {
  source = "../../modules/alb"

  environment  = local.environment
  project_name = "apim"
  vpc_id       = module.vpc.vpc_id

  public_subnet_ids     = module.vpc.public_subnet_ids
  alb_security_group_id = aws_security_group.alb.id

  webmethods_instance_id = module.ec2.webmethods_instance_id
  portal_instance_id     = module.ec2.portal_instance_id
  jenkins_instance_id    = module.ec2.jenkins_instance_id

  tags = local.tags
}

# Outputs
output "vpc_id" {
  value       = module.vpc.vpc_id
  description = "VPC ID"
}

output "private_subnet_ids" {
  value       = module.vpc.private_subnet_ids
  description = "Private subnet IDs"
}

output "public_subnet_ids" {
  value       = module.vpc.public_subnet_ids
  description = "Public subnet IDs"
}

output "kms_key_id" {
  value       = aws_kms_key.vault.id
  description = "KMS key ID for Vault"
}

output "webmethods_private_ip" {
  value       = module.ec2.webmethods_private_ip
  description = "webMethods private IP"
}

output "portal_private_ip" {
  value       = module.ec2.portal_private_ip
  description = "Portal private IP"
}

output "jenkins_private_ip" {
  value       = module.ec2.jenkins_private_ip
  description = "Jenkins private IP"
}

output "vault_private_ip" {
  value       = module.ec2.vault_private_ip
  description = "Vault private IP"
}

output "alb_dns_name" {
  value       = module.alb.alb_dns_name
  description = "ALB DNS name - Use this to access all services"
}

output "webmethods_url" {
  value       = module.alb.webmethods_url
  description = "webMethods Gateway URL"
}

output "portal_url" {
  value       = module.alb.portal_url
  description = "Developer Portal URL"
}

output "jenkins_url" {
  value       = module.alb.jenkins_url
  description = "Jenkins URL"
}

output "access_instructions" {
  value = <<-EOT

  🎉 APIM Platform deployed successfully!

  Access your services:
  - webMethods Gateway: ${module.alb.webmethods_url}
  - Developer Portal:   ${module.alb.portal_url}
  - Jenkins:           ${module.alb.jenkins_url}

  Private IPs (for Ansible):
  - webMethods: ${module.ec2.webmethods_private_ip}
  - Portal:     ${module.ec2.portal_private_ip}
  - Jenkins:    ${module.ec2.jenkins_private_ip}
  - Vault:      ${module.ec2.vault_private_ip}

  Next steps:
  1. Configure services with Ansible:
     cd ansible
     ansible-playbook -i inventory/dev.ini playbooks/site.yml

  2. Stop instances when not in use to save costs:
     ../scripts/stop-instances.sh dev
  EOT
  description = "Instructions for accessing the platform"
}
