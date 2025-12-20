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

# =============================================================================
# AUTO STOP/START SYSTEM
# =============================================================================

# IAM Role for Lambda
resource "aws_iam_role" "lambda_ec2_control" {
  name = "${local.project}-lambda-ec2-control-${local.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })

  tags = local.tags
}

resource "aws_iam_role_policy" "lambda_ec2_control" {
  name = "${local.project}-lambda-ec2-control"
  role = aws_iam_role.lambda_ec2_control.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:StartInstances",
          "ec2:StopInstances",
          "ec2:DescribeInstances"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "ec2:ResourceTag/Project" = "APIM"
          }
        }
      },
      {
        Effect   = "Allow"
        Action   = ["ec2:DescribeInstances"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:GetMetricStatistics"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# Lambda: Auto-Stop (inactivity detection)
# Uses tags to auto-discover instances - no need to update when adding new EC2s
resource "aws_lambda_function" "auto_stop" {
  filename         = data.archive_file.auto_stop.output_path
  function_name    = "${local.project}-auto-stop-${local.environment}"
  role             = aws_iam_role.lambda_ec2_control.arn
  handler          = "index.handler"
  source_code_hash = data.archive_file.auto_stop.output_base64sha256
  runtime          = "python3.11"
  timeout          = 60

  environment {
    variables = {
      PROJECT_TAG      = "APIM"
      ENVIRONMENT_TAG  = local.environment
      CPU_THRESHOLD    = "5"
      INACTIVE_MINUTES = "30"
    }
  }

  tags = local.tags
}

data "archive_file" "auto_stop" {
  type        = "zip"
  output_path = "${path.module}/lambda_auto_stop.zip"

  source {
    content  = <<-PYTHON
import boto3
import os
from datetime import datetime, timedelta

def handler(event, context):
    ec2 = boto3.client('ec2')
    cloudwatch = boto3.client('cloudwatch')

    project_tag = os.environ.get('PROJECT_TAG', 'APIM')
    environment_tag = os.environ.get('ENVIRONMENT_TAG', 'dev')
    cpu_threshold = float(os.environ.get('CPU_THRESHOLD', '5'))
    inactive_minutes = int(os.environ.get('INACTIVE_MINUTES', '30'))

    # Auto-discover instances by tags
    response = ec2.describe_instances(
        Filters=[
            {'Name': 'tag:Project', 'Values': [project_tag]},
            {'Name': 'tag:Environment', 'Values': [environment_tag]},
            {'Name': 'instance-state-name', 'Values': ['running']}
        ]
    )

    running_instances = []
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            # Check if instance has AutoStop=false tag (skip those)
            auto_stop = True
            for tag in instance.get('Tags', []):
                if tag['Key'] == 'AutoStop' and tag['Value'].lower() == 'false':
                    auto_stop = False
                    break
            if auto_stop:
                running_instances.append(instance['InstanceId'])

    if not running_instances:
        print("No running instances found (or all have AutoStop=false)")
        return {'stopped': []}

    print(f"Found {len(running_instances)} running instances: {running_instances}")

    # Check CPU for each running instance
    instances_to_stop = []
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(minutes=inactive_minutes)

    for instance_id in running_instances:
        metrics = cloudwatch.get_metric_statistics(
            Namespace='AWS/EC2',
            MetricName='CPUUtilization',
            Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=300,
            Statistics=['Average']
        )

        if metrics['Datapoints']:
            avg_cpu = sum(d['Average'] for d in metrics['Datapoints']) / len(metrics['Datapoints'])
            print(f"Instance {instance_id}: avg CPU = {avg_cpu:.2f}%")

            if avg_cpu < cpu_threshold:
                instances_to_stop.append(instance_id)
        else:
            print(f"Instance {instance_id}: no metrics yet, skipping")

    # Stop idle instances
    if instances_to_stop:
        print(f"Stopping idle instances: {instances_to_stop}")
        ec2.stop_instances(InstanceIds=instances_to_stop)
        return {'stopped': instances_to_stop}

    return {'stopped': []}
PYTHON
    filename = "index.py"
  }
}

# CloudWatch Event: Check every 10 minutes
resource "aws_cloudwatch_event_rule" "auto_stop_schedule" {
  name                = "${local.project}-auto-stop-schedule-${local.environment}"
  description         = "Check for idle instances every 10 minutes"
  schedule_expression = "rate(10 minutes)"

  tags = local.tags
}

resource "aws_cloudwatch_event_target" "auto_stop" {
  rule      = aws_cloudwatch_event_rule.auto_stop_schedule.name
  target_id = "auto-stop-lambda"
  arn       = aws_lambda_function.auto_stop.arn
}

resource "aws_lambda_permission" "auto_stop" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.auto_stop.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.auto_stop_schedule.arn
}

# Lambda: Start on demand
# Uses tags to auto-discover instances - no need to update when adding new EC2s
resource "aws_lambda_function" "start_instances" {
  filename         = data.archive_file.start_instances.output_path
  function_name    = "${local.project}-start-instances-${local.environment}"
  role             = aws_iam_role.lambda_ec2_control.arn
  handler          = "index.handler"
  source_code_hash = data.archive_file.start_instances.output_base64sha256
  runtime          = "python3.11"
  timeout          = 120

  environment {
    variables = {
      PROJECT_TAG     = "APIM"
      ENVIRONMENT_TAG = local.environment
      ALB_DNS         = aws_lb.main.dns_name
    }
  }

  tags = local.tags
}

data "archive_file" "start_instances" {
  type        = "zip"
  output_path = "${path.module}/lambda_start.zip"

  source {
    content  = <<-PYTHON
import boto3
import os

def handler(event, context):
    ec2 = boto3.client('ec2')
    project_tag = os.environ.get('PROJECT_TAG', 'APIM')
    environment_tag = os.environ.get('ENVIRONMENT_TAG', 'dev')
    alb_dns = os.environ.get('ALB_DNS', '')

    # Auto-discover stopped instances by tags
    response = ec2.describe_instances(
        Filters=[
            {'Name': 'tag:Project', 'Values': [project_tag]},
            {'Name': 'tag:Environment', 'Values': [environment_tag]},
            {'Name': 'instance-state-name', 'Values': ['stopped']}
        ]
    )

    stopped_instances = []
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            stopped_instances.append(instance['InstanceId'])

    # Also check running instances
    running_response = ec2.describe_instances(
        Filters=[
            {'Name': 'tag:Project', 'Values': [project_tag]},
            {'Name': 'tag:Environment', 'Values': [environment_tag]},
            {'Name': 'instance-state-name', 'Values': ['running']}
        ]
    )
    running_count = sum(len(r['Instances']) for r in running_response['Reservations'])

    if stopped_instances:
        print(f"Starting {len(stopped_instances)} instances: {stopped_instances}")
        ec2.start_instances(InstanceIds=stopped_instances)

        # Wait for instances to be running
        waiter = ec2.get_waiter('instance_running')
        waiter.wait(InstanceIds=stopped_instances, WaiterConfig={'Delay': 5, 'MaxAttempts': 24})

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'text/html'},
            'body': f'''
                <html>
                <head>
                    <meta http-equiv="refresh" content="90;url=http://{alb_dns}/gateway">
                    <style>
                        body {{ font-family: Arial; padding: 40px; background: #f5f5f5; }}
                        .container {{ background: white; padding: 30px; border-radius: 8px; max-width: 500px; margin: auto; }}
                        h1 {{ color: #2e7d32; }}
                        .loader {{ border: 4px solid #f3f3f3; border-top: 4px solid #2e7d32; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 20px auto; }}
                        @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>APIM Starting...</h1>
                        <div class="loader"></div>
                        <p><strong>{len(stopped_instances)}</strong> instance(s) starting</p>
                        <p>Please wait ~90 seconds for services to initialize...</p>
                        <p><a href="http://{alb_dns}/gateway">Click here if not redirected</a></p>
                    </div>
                </body>
                </html>
            '''
        }

    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'text/html'},
        'body': f'''
            <html>
            <head><meta http-equiv="refresh" content="3;url=http://{alb_dns}/gateway"></head>
            <body style="font-family: Arial; padding: 40px;">
                <h1 style="color: #2e7d32;">APIM Already Running</h1>
                <p>{running_count} instance(s) running</p>
                <p>Redirecting to gateway...</p>
            </body>
            </html>
        '''
    }
PYTHON
    filename = "index.py"
  }
}

# API Gateway for start endpoint
resource "aws_apigatewayv2_api" "start" {
  name          = "${local.project}-start-api-${local.environment}"
  protocol_type = "HTTP"

  tags = local.tags
}

resource "aws_apigatewayv2_integration" "start" {
  api_id                 = aws_apigatewayv2_api.start.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.start_instances.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "start" {
  api_id    = aws_apigatewayv2_api.start.id
  route_key = "GET /start"
  target    = "integrations/${aws_apigatewayv2_integration.start.id}"
}

resource "aws_apigatewayv2_stage" "start" {
  api_id      = aws_apigatewayv2_api.start.id
  name        = "$default"
  auto_deploy = true

  tags = local.tags
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.start_instances.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.start.execution_arn}/*/*"
}

# Outputs for start/stop system
output "start_url" {
  value       = "${aws_apigatewayv2_api.start.api_endpoint}/start"
  description = "URL to start instances on demand"
}

output "auto_stop_info" {
  value       = "Instances will auto-stop after 30 min of inactivity (CPU < 5%)"
  description = "Auto-stop configuration"
}
