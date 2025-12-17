# Outputs for IAM module

# Instance Profile Names
output "webmethods_instance_profile" {
  value       = aws_iam_instance_profile.webmethods.name
  description = "webMethods instance profile name"
}

output "portal_instance_profile" {
  value       = aws_iam_instance_profile.portal.name
  description = "Portal instance profile name"
}

output "jenkins_instance_profile" {
  value       = aws_iam_instance_profile.jenkins.name
  description = "Jenkins instance profile name"
}

output "vault_instance_profile" {
  value       = aws_iam_instance_profile.vault.name
  description = "Vault instance profile name"
}

# Role ARNs (optional, for reference)
output "webmethods_role_arn" {
  value       = aws_iam_role.webmethods.arn
  description = "webMethods IAM role ARN"
}

output "portal_role_arn" {
  value       = aws_iam_role.portal.arn
  description = "Portal IAM role ARN"
}

output "jenkins_role_arn" {
  value       = aws_iam_role.jenkins.arn
  description = "Jenkins IAM role ARN"
}

output "vault_role_arn" {
  value       = aws_iam_role.vault.arn
  description = "Vault IAM role ARN"
}
