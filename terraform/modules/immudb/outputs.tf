output "immudb_instance_id" {
  description = "ID der ImmuDB EC2 Instanz"
  value       = aws_instance.immudb.id
}

output "immudb_private_ip" {
  description = "Private IP der ImmuDB Instanz"
  value       = aws_instance.immudb.private_ip
}

output "immudb_security_group_id" {
  description = "ID der ImmuDB Security Group"
  value       = aws_security_group.immudb.id
}

output "immudb_backup_bucket" {
  description = "Name des S3 Backup Buckets"
  value       = aws_s3_bucket.immudb_backup.id
}
