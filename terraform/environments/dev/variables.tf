# Variables for DEV environment

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "eu-west-1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "dev"
}

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of availability zones"
  type        = list(string)
  default     = ["eu-west-1a", "eu-west-1b", "eu-west-1c"]
}

# EKS Variables
variable "kubernetes_version" {
  description = "Kubernetes version"
  type        = string
  default     = "1.29"
}

variable "node_instance_types" {
  description = "EC2 instance types for EKS worker nodes"
  type        = list(string)
  default     = ["t3.large"]  # Upgraded from t3.medium for Redpanda/Kafka
}

variable "node_desired_size" {
  description = "Desired number of EKS worker nodes"
  type        = number
  default     = 3  # Increased for AWX and additional workloads
}

variable "node_min_size" {
  description = "Minimum number of EKS worker nodes"
  type        = number
  default     = 1
}

variable "node_max_size" {
  description = "Maximum number of EKS worker nodes"
  type        = number
  default     = 5
}

# RDS Variables
variable "rds_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.small"
}

variable "rds_allocated_storage" {
  description = "RDS allocated storage in GB"
  type        = number
  default     = 20
}

# OpenSearch Variables
variable "opensearch_engine_version" {
  description = "OpenSearch engine version"
  type        = string
  default     = "OpenSearch_2.11"
}

variable "opensearch_instance_type" {
  description = "OpenSearch instance type"
  type        = string
  default     = "t3.small.search"
}

variable "opensearch_instance_count" {
  description = "Number of OpenSearch instances"
  type        = number
  default     = 1
}

variable "opensearch_ebs_volume_size" {
  description = "OpenSearch EBS volume size in GB"
  type        = number
  default     = 20
}

# NOTE: Sensitive passwords are now managed via AWS Secrets Manager
# See terraform/modules/secrets for the secrets module
# The opensearch_master_password is auto-generated and stored in AWS Secrets Manager
# To retrieve: aws secretsmanager get-secret-value --secret-id apim/dev/opensearch-master
