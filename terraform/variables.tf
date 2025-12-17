variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "eu-west-1"
}

variable "environment" {
  description = "Environment name (dev, test, prod)"
  type        = string
  default     = "dev"
}

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones"
  type        = list(string)
  default     = ["eu-west-1a", "eu-west-1b"]
}

variable "project_name" {
  description = "Project name"
  type        = string
  default     = "apim"
}

variable "domain_name" {
  description = "Domain name for the platform"
  type        = string
  default     = "apim-dev.votredomaine.com"
}

variable "tags" {
  description = "Common tags"
  type        = map(string)
  default     = {}
}
