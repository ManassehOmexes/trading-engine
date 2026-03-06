output "clickhouse_instance_id" {
  description = "ID der ClickHouse EC2 Instanz"
  value       = aws_instance.clickhouse.id
}

output "clickhouse_private_ip" {
  description = "Private IP der ClickHouse Instanz"
  value       = aws_instance.clickhouse.private_ip
}

output "clickhouse_security_group_id" {
  description = "ID der ClickHouse Security Group"
  value       = aws_security_group.clickhouse.id
}

output "clickhouse_backup_bucket" {
  description = "Name des S3 Backup Buckets"
  value       = aws_s3_bucket.clickhouse_backup.id
}
