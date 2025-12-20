# Variables for APIM Platform v2 - Simplified

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
