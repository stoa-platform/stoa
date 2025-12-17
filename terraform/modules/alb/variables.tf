variable "environment" {
  description = "Environment name"
  type        = string
}

variable "project_name" {
  description = "Project name"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "public_subnet_ids" {
  description = "List of public subnet IDs for ALB"
  type        = list(string)
}

variable "alb_security_group_id" {
  description = "Security group ID for ALB"
  type        = string
}

variable "webmethods_instance_id" {
  description = "webMethods instance ID"
  type        = string
}

variable "portal_instance_id" {
  description = "Portal instance ID"
  type        = string
}

variable "jenkins_instance_id" {
  description = "Jenkins instance ID"
  type        = string
}

variable "tags" {
  description = "Common tags"
  type        = map(string)
  default     = {}
}
