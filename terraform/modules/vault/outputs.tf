output "vault_security_group_id" {
  description = "ID der Vault Security Group"
  value       = aws_security_group.vault.id
}

output "vault_iam_role_arn" {
  description = "ARN der Vault IAM Role"
  value       = aws_iam_role.vault.arn
}

output "vault_kms_key_arn" {
  description = "ARN des KMS Keys fuer Vault Auto-Unseal"
  value       = aws_kms_key.vault.arn
}

output "vault_storage_bucket" {
  description = "Name des S3 Buckets fuer Vault Storage"
  value       = aws_s3_bucket.vault_storage.id
}
