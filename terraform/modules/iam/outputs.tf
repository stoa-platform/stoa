output "webmethods_role_arn" {
  description = "ARN of webMethods IAM role"
  value       = aws_iam_role.webmethods.arn
}

output "webmethods_instance_profile_name" {
  description = "Name of webMethods instance profile"
  value       = aws_iam_instance_profile.webmethods.name
}

output "portal_role_arn" {
  description = "ARN of Portal IAM role"
  value       = aws_iam_role.portal.arn
}

output "portal_instance_profile_name" {
  description = "Name of Portal instance profile"
  value       = aws_iam_instance_profile.portal.name
}

output "jenkins_role_arn" {
  description = "ARN of Jenkins IAM role"
  value       = aws_iam_role.jenkins.arn
}

output "jenkins_instance_profile_name" {
  description = "Name of Jenkins instance profile"
  value       = aws_iam_instance_profile.jenkins.name
}

output "vault_role_arn" {
  description = "ARN of Vault IAM role"
  value       = aws_iam_role.vault.arn
}

output "vault_instance_profile_name" {
  description = "Name of Vault instance profile"
  value       = aws_iam_instance_profile.vault.name
}
