output "immudb_instance_id" {
  value = aws_instance.immudb.id
}

output "immudb_private_ip" {
  value = aws_instance.immudb.private_ip
}

output "immudb_security_group_id" {
  value = aws_security_group.immudb.id
}

output "immudb_backup_bucket" {
  value = aws_s3_bucket.immudb.id
}
