# IAM Role for webMethods Gateway
resource "aws_iam_role" "webmethods" {
  name = "${var.project_name}-webmethods-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = var.tags
}

# IAM Role for Developer Portal
resource "aws_iam_role" "portal" {
  name = "${var.project_name}-portal-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = var.tags
}

# IAM Role for Jenkins
resource "aws_iam_role" "jenkins" {
  name = "${var.project_name}-jenkins-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = var.tags
}

# IAM Role for Vault
resource "aws_iam_role" "vault" {
  name = "${var.project_name}-vault-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = var.tags
}

# Common policy for SSM access
resource "aws_iam_policy" "ssm_access" {
  name        = "${var.project_name}-ssm-access-${var.environment}"
  description = "Allow SSM Session Manager access"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ssm:UpdateInstanceInformation",
          "ssmmessages:CreateControlChannel",
          "ssmmessages:CreateDataChannel",
          "ssmmessages:OpenControlChannel",
          "ssmmessages:OpenDataChannel"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetEncryptionConfiguration"
        ]
        Resource = "*"
      }
    ]
  })

  tags = var.tags
}

# Common policy for CloudWatch Logs
resource "aws_iam_policy" "cloudwatch_logs" {
  name        = "${var.project_name}-cloudwatch-logs-${var.environment}"
  description = "Allow writing to CloudWatch Logs"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })

  tags = var.tags
}

# Policy for S3 access (artifacts, backups)
resource "aws_iam_policy" "s3_access" {
  name        = "${var.project_name}-s3-access-${var.environment}"
  description = "Allow S3 access for artifacts and backups"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket",
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Resource = [
          "arn:aws:s3:::${var.project_name}-*-${var.environment}",
          "arn:aws:s3:::${var.project_name}-*-${var.environment}/*"
        ]
      }
    ]
  })

  tags = var.tags
}

# Policy for Vault (S3 backend and KMS)
resource "aws_iam_policy" "vault_s3_kms" {
  name        = "${var.project_name}-vault-s3-kms-${var.environment}"
  description = "Allow Vault S3 backend and KMS auto-unseal"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::${var.project_name}-vault-storage-${var.environment}",
          "arn:aws:s3:::${var.project_name}-vault-storage-${var.environment}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:DescribeKey"
        ]
        Resource = "*"
      }
    ]
  })

  tags = var.tags
}

# Policy for Jenkins (full AWS access for Terraform/Ansible)
resource "aws_iam_policy" "jenkins_admin" {
  name        = "${var.project_name}-jenkins-admin-${var.environment}"
  description = "Allow Jenkins to manage AWS resources"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:*",
          "ecs:*",
          "ecr:*",
          "s3:*",
          "dynamodb:*",
          "iam:PassRole",
          "iam:GetRole",
          "iam:ListRoles",
          "logs:*",
          "cloudwatch:*"
        ]
        Resource = "*"
      }
    ]
  })

  tags = var.tags
}

# Attach policies to roles
resource "aws_iam_role_policy_attachment" "webmethods_ssm" {
  role       = aws_iam_role.webmethods.name
  policy_arn = aws_iam_policy.ssm_access.arn
}

resource "aws_iam_role_policy_attachment" "webmethods_cloudwatch" {
  role       = aws_iam_role.webmethods.name
  policy_arn = aws_iam_policy.cloudwatch_logs.arn
}

resource "aws_iam_role_policy_attachment" "webmethods_s3" {
  role       = aws_iam_role.webmethods.name
  policy_arn = aws_iam_policy.s3_access.arn
}

resource "aws_iam_role_policy_attachment" "portal_ssm" {
  role       = aws_iam_role.portal.name
  policy_arn = aws_iam_policy.ssm_access.arn
}

resource "aws_iam_role_policy_attachment" "portal_cloudwatch" {
  role       = aws_iam_role.portal.name
  policy_arn = aws_iam_policy.cloudwatch_logs.arn
}

resource "aws_iam_role_policy_attachment" "jenkins_ssm" {
  role       = aws_iam_role.jenkins.name
  policy_arn = aws_iam_policy.ssm_access.arn
}

resource "aws_iam_role_policy_attachment" "jenkins_cloudwatch" {
  role       = aws_iam_role.jenkins.name
  policy_arn = aws_iam_policy.cloudwatch_logs.arn
}

resource "aws_iam_role_policy_attachment" "jenkins_s3" {
  role       = aws_iam_role.jenkins.name
  policy_arn = aws_iam_policy.s3_access.arn
}

resource "aws_iam_role_policy_attachment" "jenkins_admin" {
  role       = aws_iam_role.jenkins.name
  policy_arn = aws_iam_policy.jenkins_admin.arn
}

resource "aws_iam_role_policy_attachment" "vault_ssm" {
  role       = aws_iam_role.vault.name
  policy_arn = aws_iam_policy.ssm_access.arn
}

resource "aws_iam_role_policy_attachment" "vault_cloudwatch" {
  role       = aws_iam_role.vault.name
  policy_arn = aws_iam_policy.cloudwatch_logs.arn
}

resource "aws_iam_role_policy_attachment" "vault_s3_kms" {
  role       = aws_iam_role.vault.name
  policy_arn = aws_iam_policy.vault_s3_kms.arn
}

# Instance Profiles
resource "aws_iam_instance_profile" "webmethods" {
  name = "${var.project_name}-webmethods-profile-${var.environment}"
  role = aws_iam_role.webmethods.name

  tags = var.tags
}

resource "aws_iam_instance_profile" "portal" {
  name = "${var.project_name}-portal-profile-${var.environment}"
  role = aws_iam_role.portal.name

  tags = var.tags
}

resource "aws_iam_instance_profile" "jenkins" {
  name = "${var.project_name}-jenkins-profile-${var.environment}"
  role = aws_iam_role.jenkins.name

  tags = var.tags
}

resource "aws_iam_instance_profile" "vault" {
  name = "${var.project_name}-vault-profile-${var.environment}"
  role = aws_iam_role.vault.name

  tags = var.tags
}
