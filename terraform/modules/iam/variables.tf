variable "environment" {
  description = "Environment name"
  type        = string
}

variable "project_name" {
  description = "Project name"
  type        = string
}

variable "tags" {
  description = "Additional tags"
  type        = map(string)
  default     = {}
}
