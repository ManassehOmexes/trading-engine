output "clickhouse_instance_id" {
  value = aws_instance.clickhouse.id
}

output "clickhouse_private_ip" {
  value = aws_instance.clickhouse.private_ip
}

output "clickhouse_security_group_id" {
  value = aws_security_group.clickhouse.id
}

output "clickhouse_backup_bucket" {
  value = aws_s3_bucket.clickhouse.id
}
