output "msk_cluster_arn" {
  description = "ARN des MSK Clusters"
  value       = aws_msk_cluster.main.arn
}

output "msk_bootstrap_brokers" {
  description = "Kafka Bootstrap Broker Adressen (Plaintext)"
  value       = aws_msk_cluster.main.bootstrap_brokers
}

output "msk_bootstrap_brokers_tls" {
  description = "Kafka Bootstrap Broker Adressen (TLS)"
  value       = aws_msk_cluster.main.bootstrap_brokers_tls
}

output "msk_security_group_id" {
  description = "ID der MSK Security Group"
  value       = aws_security_group.msk.id
}
