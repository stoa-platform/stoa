# Variables for DEV environment

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS Region"
  type        = string
  default     = "eu-west-1"
}

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of availability zones"
  type        = list(string)
  default     = ["eu-west-1a", "eu-west-1b"]
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "apim"
}

variable "webmethods_instance_type" {
  description = "Instance type for webMethods Gateway"
  type        = string
  default     = "t3.large"
}

variable "portal_instance_type" {
  description = "Instance type for Developer Portal"
  type        = string
  default     = "t3.medium"
}

variable "jenkins_instance_type" {
  description = "Instance type for Jenkins"
  type        = string
  default     = "t3.medium"
}

variable "vault_instance_type" {
  description = "Instance type for HashiCorp Vault"
  type        = string
  default     = "t3.small"
}

variable "opensearch_instance_type" {
  description = "Instance type for OpenSearch"
  type        = string
  default     = "t3.small.search"
}

variable "opensearch_volume_size" {
  description = "Volume size in GB for OpenSearch"
  type        = number
  default     = 20
}

variable "control_plane_cpu" {
  description = "CPU units for Control Plane Fargate task (256 = 0.25 vCPU)"
  type        = number
  default     = 256
}

variable "control_plane_memory" {
  description = "Memory in MB for Control Plane Fargate task"
  type        = number
  default     = 512
}

variable "tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default = {
    Project     = "APIM"
    Environment = "dev"
    ManagedBy   = "Terraform"
  }
}
