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

variable "private_subnet_ids" {
  description = "List of private subnet IDs"
  type        = list(string)
}

variable "webmethods_instance_type" {
  description = "Instance type for webMethods"
  type        = string
  default     = "t3.large"
}

variable "portal_instance_type" {
  description = "Instance type for Portal"
  type        = string
  default     = "t3.medium"
}

variable "jenkins_instance_type" {
  description = "Instance type for Jenkins"
  type        = string
  default     = "t3.medium"
}

variable "vault_instance_type" {
  description = "Instance type for Vault"
  type        = string
  default     = "t3.small"
}

variable "webmethods_security_group_id" {
  description = "Security group ID for webMethods"
  type        = string
}

variable "portal_security_group_id" {
  description = "Security group ID for Portal"
  type        = string
}

variable "jenkins_security_group_id" {
  description = "Security group ID for Jenkins"
  type        = string
}

variable "vault_security_group_id" {
  description = "Security group ID for Vault"
  type        = string
}

variable "webmethods_instance_profile" {
  description = "IAM instance profile for webMethods"
  type        = string
}

variable "portal_instance_profile" {
  description = "IAM instance profile for Portal"
  type        = string
}

variable "jenkins_instance_profile" {
  description = "IAM instance profile for Jenkins"
  type        = string
}

variable "vault_instance_profile" {
  description = "IAM instance profile for Vault"
  type        = string
}

variable "kms_key_id" {
  description = "KMS key ID for Vault auto-unseal"
  type        = string
}

variable "vault_bucket" {
  description = "S3 bucket for Vault storage"
  type        = string
}

variable "artifacts_bucket" {
  description = "S3 bucket for artifacts"
  type        = string
}

variable "tags" {
  description = "Common tags"
  type        = map(string)
  default     = {}
}
