# Application Load Balancer Module for APIM Platform

# Application Load Balancer
resource "aws_lb" "main" {
  name               = "${var.project_name}-alb-${var.environment}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.alb_security_group_id]
  subnets            = var.public_subnet_ids

  enable_deletion_protection = false
  enable_http2              = true

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-alb-${var.environment}"
    }
  )
}

# Target Group for webMethods (port 9072)
resource "aws_lb_target_group" "webmethods" {
  name     = "${var.project_name}-webmethods-${var.environment}"
  port     = 9072
  protocol = "HTTP"
  vpc_id   = var.vpc_id

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    path                = "/rest/apigateway/health"
    matcher             = "200"
  }

  deregistration_delay = 30

  tags = merge(
    var.tags,
    {
      Name    = "webmethods-tg"
      Service = "webMethods"
    }
  )
}

# Target Group for Portal (port 18101)
resource "aws_lb_target_group" "portal" {
  name     = "${var.project_name}-portal-${var.environment}"
  port     = 18101
  protocol = "HTTP"
  vpc_id   = var.vpc_id

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    path                = "/portal"
    matcher             = "200,302"
  }

  deregistration_delay = 30

  tags = merge(
    var.tags,
    {
      Name    = "portal-tg"
      Service = "Portal"
    }
  )
}

# Target Group for Jenkins (port 8080)
resource "aws_lb_target_group" "jenkins" {
  name     = "${var.project_name}-jenkins-${var.environment}"
  port     = 8080
  protocol = "HTTP"
  vpc_id   = var.vpc_id

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    path                = "/login"
    matcher             = "200"
  }

  deregistration_delay = 30

  tags = merge(
    var.tags,
    {
      Name    = "jenkins-tg"
      Service = "Jenkins"
    }
  )
}

# Target Group Attachments
resource "aws_lb_target_group_attachment" "webmethods" {
  target_group_arn = aws_lb_target_group.webmethods.arn
  target_id        = var.webmethods_instance_id
  port             = 9072
}

resource "aws_lb_target_group_attachment" "portal" {
  target_group_arn = aws_lb_target_group.portal.arn
  target_id        = var.portal_instance_id
  port             = 18101
}

resource "aws_lb_target_group_attachment" "jenkins" {
  target_group_arn = aws_lb_target_group.jenkins.arn
  target_id        = var.jenkins_instance_id
  port             = 8080
}

# HTTP Listener (redirects to HTTPS if cert is configured, otherwise serves directly)
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type = "fixed-response"

    fixed_response {
      content_type = "text/html"
      message_body = <<-EOF
        <html>
          <head><title>APIM Platform</title></head>
          <body>
            <h1>Welcome to APIM Platform</h1>
            <p>Available services:</p>
            <ul>
              <li><a href="/webmethods">webMethods API Gateway (port 9072)</a></li>
              <li><a href="/portal">Developer Portal (port 18101)</a></li>
              <li><a href="/jenkins">Jenkins (port 8080)</a></li>
            </ul>
            <p>Use path-based routing or direct port access</p>
          </body>
        </html>
      EOF
      status_code  = "200"
    }
  }
}

# Listener Rule for webMethods (path /webmethods/*)
resource "aws_lb_listener_rule" "webmethods_path" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.webmethods.arn
  }

  condition {
    path_pattern {
      values = ["/webmethods*", "/rest/*", "/invoke/*"]
    }
  }
}

# Listener Rule for Portal (path /portal/*)
resource "aws_lb_listener_rule" "portal_path" {
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

# Listener Rule for Jenkins (path /jenkins/*)
resource "aws_lb_listener_rule" "jenkins_path" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 300

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.jenkins.arn
  }

  condition {
    path_pattern {
      values = ["/jenkins*"]
    }
  }
}

# Additional listeners for direct port access
resource "aws_lb_listener" "webmethods_direct" {
  load_balancer_arn = aws_lb.main.arn
  port              = "9072"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.webmethods.arn
  }
}

resource "aws_lb_listener" "portal_direct" {
  load_balancer_arn = aws_lb.main.arn
  port              = "18101"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.portal.arn
  }
}

resource "aws_lb_listener" "jenkins_direct" {
  load_balancer_arn = aws_lb.main.arn
  port              = "8080"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.jenkins.arn
  }
}

# Outputs
output "alb_dns_name" {
  value       = aws_lb.main.dns_name
  description = "DNS name of the load balancer"
}

output "alb_arn" {
  value       = aws_lb.main.arn
  description = "ARN of the load balancer"
}

output "alb_zone_id" {
  value       = aws_lb.main.zone_id
  description = "Zone ID of the load balancer"
}

output "webmethods_target_group_arn" {
  value       = aws_lb_target_group.webmethods.arn
  description = "ARN of webMethods target group"
}

output "webmethods_url" {
  value       = "http://${aws_lb.main.dns_name}:9072"
  description = "URL to access webMethods Gateway"
}

output "portal_url" {
  value       = "http://${aws_lb.main.dns_name}:18101/portal"
  description = "URL to access Developer Portal"
}

output "jenkins_url" {
  value       = "http://${aws_lb.main.dns_name}:8080"
  description = "URL to access Jenkins"
}
