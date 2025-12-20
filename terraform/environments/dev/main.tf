# APIM Platform - Simplified Architecture v2
# Only webMethods + Portal + ALB (HTTP only)

locals {
  environment = "dev"
  aws_region  = "eu-west-1"
  project     = "apim"

  tags = {
    Project     = "APIM"
    Environment = local.environment
    ManagedBy   = "Terraform"
  }
}

# =============================================================================
# VPC MODULE
# =============================================================================
module "vpc" {
  source = "../../modules/vpc"

  vpc_cidr           = "10.0.0.0/16"
  availability_zones = ["eu-west-1a", "eu-west-1b"]
  environment        = local.environment
  project_name       = local.project
  aws_region         = local.aws_region
  tags               = local.tags
}

# =============================================================================
# S3 BUCKET (artifacts only)
# =============================================================================
resource "aws_s3_bucket" "artifacts" {
  bucket = "${local.project}-artifacts-${local.environment}"
  tags   = merge(local.tags, { Name = "APIM Artifacts" })
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  versioning_configuration {
    status = "Enabled"
  }
}

# =============================================================================
# SECURITY GROUPS
# =============================================================================

# ALB Security Group - HTTP only for now
resource "aws_security_group" "alb" {
  name        = "${local.project}-alb-sg-${local.environment}"
  description = "Security group for Application Load Balancer"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTP from internet"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.tags, { Name = "${local.project}-alb-sg" })
}

# webMethods Security Group
resource "aws_security_group" "webmethods" {
  name        = "${local.project}-webmethods-sg-${local.environment}"
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

  tags = merge(local.tags, { Name = "${local.project}-webmethods-sg" })
}

# Portal Security Group
resource "aws_security_group" "portal" {
  name        = "${local.project}-portal-sg-${local.environment}"
  description = "Security group for Developer Portal"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port       = 18101
    to_port         = 18101
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
    description     = "Portal from ALB"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.tags, { Name = "${local.project}-portal-sg" })
}

# =============================================================================
# IAM
# =============================================================================
resource "aws_iam_role" "ec2" {
  name = "${local.project}-ec2-role-${local.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })

  tags = local.tags
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "s3_access" {
  name = "${local.project}-s3-access"
  role = aws_iam_role.ec2.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
      Resource = [aws_s3_bucket.artifacts.arn, "${aws_s3_bucket.artifacts.arn}/*"]
    }]
  })
}

resource "aws_iam_instance_profile" "ec2" {
  name = "${local.project}-ec2-profile-${local.environment}"
  role = aws_iam_role.ec2.name
}

# =============================================================================
# EC2 INSTANCES
# =============================================================================
data "aws_ami" "amazon_linux" {
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

# webMethods API Gateway
resource "aws_instance" "webmethods" {
  ami                    = data.aws_ami.amazon_linux.id
  instance_type          = var.webmethods_instance_type
  subnet_id              = module.vpc.private_subnet_ids[0]
  vpc_security_group_ids = [aws_security_group.webmethods.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2.name

  root_block_device {
    volume_size = 50
    volume_type = "gp3"
    encrypted   = true
  }

  tags = merge(local.tags, {
    Name    = "${local.project}-webmethods-${local.environment}"
    Service = "webMethods"
  })

  lifecycle {
    ignore_changes = [ami]
  }
}

# Developer Portal
resource "aws_instance" "portal" {
  ami                    = data.aws_ami.amazon_linux.id
  instance_type          = var.portal_instance_type
  subnet_id              = module.vpc.private_subnet_ids[0] # Same AZ as webMethods
  vpc_security_group_ids = [aws_security_group.portal.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2.name

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
    encrypted   = true
  }

  tags = merge(local.tags, {
    Name    = "${local.project}-portal-${local.environment}"
    Service = "Portal"
  })

  depends_on = [aws_instance.webmethods]

  lifecycle {
    ignore_changes = [ami]
  }
}

# =============================================================================
# APPLICATION LOAD BALANCER
# =============================================================================
resource "aws_lb" "main" {
  name               = "${local.project}-alb-${local.environment}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = module.vpc.public_subnet_ids

  tags = local.tags
}

# Target Groups
resource "aws_lb_target_group" "webmethods" {
  name     = "${local.project}-wm-tg-${local.environment}"
  port     = 9072
  protocol = "HTTP"
  vpc_id   = module.vpc.vpc_id

  health_check {
    enabled             = true
    path                = "/rest/apigateway/health"
    matcher             = "200"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
  }

  tags = merge(local.tags, { Service = "webMethods" })
}

resource "aws_lb_target_group" "portal" {
  name     = "${local.project}-portal-tg-${local.environment}"
  port     = 18101
  protocol = "HTTP"
  vpc_id   = module.vpc.vpc_id

  health_check {
    enabled             = true
    path                = "/portal"
    matcher             = "200,302"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
  }

  tags = merge(local.tags, { Service = "Portal" })
}

# Target Group Attachments
resource "aws_lb_target_group_attachment" "webmethods" {
  target_group_arn = aws_lb_target_group.webmethods.arn
  target_id        = aws_instance.webmethods.id
  port             = 9072
}

resource "aws_lb_target_group_attachment" "portal" {
  target_group_arn = aws_lb_target_group.portal.arn
  target_id        = aws_instance.portal.id
  port             = 18101
}

# HTTP Listener
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/html"
      message_body = "<h1>APIM Platform</h1><p>Use /gateway or /portal paths</p>"
      status_code  = "200"
    }
  }
}

# Listener Rules
resource "aws_lb_listener_rule" "webmethods" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.webmethods.arn
  }

  condition {
    path_pattern {
      values = ["/gateway*", "/rest/*", "/invoke/*", "/apigateway/*"]
    }
  }
}

resource "aws_lb_listener_rule" "portal" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 200

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.portal.arn
  }

  condition {
    path_pattern {
      values = ["/portal*"]
    }
  }
}

# =============================================================================
# OUTPUTS
# =============================================================================
output "vpc_id" {
  value       = module.vpc.vpc_id
  description = "VPC ID"
}

output "alb_dns_name" {
  value       = aws_lb.main.dns_name
  description = "ALB DNS name"
}

output "webmethods_private_ip" {
  value       = aws_instance.webmethods.private_ip
  description = "webMethods private IP"
}

output "portal_private_ip" {
  value       = aws_instance.portal.private_ip
  description = "Portal private IP"
}

output "access_instructions" {
  value = <<-EOT

  APIM Platform v2 - Simplified Architecture

  ALB URL: http://${aws_lb.main.dns_name}

  Services:
  - webMethods: http://${aws_lb.main.dns_name}/gateway
  - Portal:     http://${aws_lb.main.dns_name}/portal

  Private IPs (for Ansible/SSM):
  - webMethods: ${aws_instance.webmethods.private_ip}
  - Portal:     ${aws_instance.portal.private_ip}

  Connect via SSM:
    aws ssm start-session --target ${aws_instance.webmethods.id}

  EOT
  description = "Access instructions"
}

output "webmethods_instance_id" {
  value       = aws_instance.webmethods.id
  description = "webMethods EC2 instance ID"
}

output "portal_instance_id" {
  value       = aws_instance.portal.id
  description = "Portal EC2 instance ID"
}
