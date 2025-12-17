# EC2 Module for APIM Platform
# Creates instances for webMethods, Portal, Jenkins, and Vault

# Data source for latest Amazon Linux 2 AMI
data "aws_ami" "amazon_linux_2" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["amzn2-ami-hvm-*-x86_64-gp2"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# webMethods API Gateway Instance
resource "aws_instance" "webmethods" {
  ami                    = data.aws_ami.amazon_linux_2.id
  instance_type          = var.webmethods_instance_type
  subnet_id              = var.private_subnet_ids[0]
  vpc_security_group_ids = [var.webmethods_security_group_id]
  iam_instance_profile   = var.webmethods_instance_profile

  root_block_device {
    volume_size           = 50
    volume_type           = "gp3"
    delete_on_termination = true
    encrypted             = true
  }

  user_data = templatefile("${path.module}/userdata/webmethods.sh", {
    environment     = var.environment
    artifacts_bucket = var.artifacts_bucket
  })

  tags = merge(
    var.tags,
    {
      Name     = "apim-webmethods-${var.environment}"
      Service  = "webMethods"
      AutoStop = "true"
    }
  )

  lifecycle {
    ignore_changes = [ami]
  }
}

# Developer Portal Instance
resource "aws_instance" "portal" {
  ami                    = data.aws_ami.amazon_linux_2.id
  instance_type          = var.portal_instance_type
  subnet_id              = var.private_subnet_ids[1]
  vpc_security_group_ids = [var.portal_security_group_id]
  iam_instance_profile   = var.portal_instance_profile

  root_block_device {
    volume_size           = 30
    volume_type           = "gp3"
    delete_on_termination = true
    encrypted             = true
  }

  user_data = templatefile("${path.module}/userdata/portal.sh", {
    environment     = var.environment
    webmethods_ip   = aws_instance.webmethods.private_ip
  })

  tags = merge(
    var.tags,
    {
      Name     = "apim-portal-${var.environment}"
      Service  = "Portal"
      AutoStop = "true"
    }
  )

  depends_on = [aws_instance.webmethods]

  lifecycle {
    ignore_changes = [ami]
  }
}

# Jenkins Instance
resource "aws_instance" "jenkins" {
  ami                    = data.aws_ami.amazon_linux_2.id
  instance_type          = var.jenkins_instance_type
  subnet_id              = var.private_subnet_ids[0]
  vpc_security_group_ids = [var.jenkins_security_group_id]
  iam_instance_profile   = var.jenkins_instance_profile

  root_block_device {
    volume_size           = 30
    volume_type           = "gp3"
    delete_on_termination = true
    encrypted             = true
  }

  user_data = templatefile("${path.module}/userdata/jenkins.sh", {
    environment = var.environment
  })

  tags = merge(
    var.tags,
    {
      Name     = "apim-jenkins-${var.environment}"
      Service  = "Jenkins"
      AutoStop = "true"
    }
  )

  lifecycle {
    ignore_changes = [ami]
  }
}

# Vault Instance
resource "aws_instance" "vault" {
  ami                    = data.aws_ami.amazon_linux_2.id
  instance_type          = var.vault_instance_type
  subnet_id              = var.private_subnet_ids[1]
  vpc_security_group_ids = [var.vault_security_group_id]
  iam_instance_profile   = var.vault_instance_profile

  root_block_device {
    volume_size           = 20
    volume_type           = "gp3"
    delete_on_termination = true
    encrypted             = true
  }

  user_data = templatefile("${path.module}/userdata/vault.sh", {
    environment  = var.environment
    kms_key_id   = var.kms_key_id
    vault_bucket = var.vault_bucket
  })

  tags = merge(
    var.tags,
    {
      Name     = "apim-vault-${var.environment}"
      Service  = "Vault"
      AutoStop = "false"  # Vault should stay running
    }
  )

  lifecycle {
    ignore_changes = [ami]
  }
}

# Outputs
output "webmethods_instance_id" {
  value       = aws_instance.webmethods.id
  description = "webMethods instance ID"
}

output "webmethods_private_ip" {
  value       = aws_instance.webmethods.private_ip
  description = "webMethods private IP"
}

output "portal_instance_id" {
  value       = aws_instance.portal.id
  description = "Portal instance ID"
}

output "portal_private_ip" {
  value       = aws_instance.portal.private_ip
  description = "Portal private IP"
}

output "jenkins_instance_id" {
  value       = aws_instance.jenkins.id
  description = "Jenkins instance ID"
}

output "jenkins_private_ip" {
  value       = aws_instance.jenkins.private_ip
  description = "Jenkins private IP"
}

output "vault_instance_id" {
  value       = aws_instance.vault.id
  description = "Vault instance ID"
}

output "vault_private_ip" {
  value       = aws_instance.vault.private_ip
  description = "Vault private IP"
}
