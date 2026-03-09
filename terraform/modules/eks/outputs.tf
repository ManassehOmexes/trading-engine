output "cluster_name" {
  description = "Name des EKS Clusters"
  value       = aws_eks_cluster.main.name
}

output "cluster_endpoint" {
  description = "API Endpoint des EKS Clusters"
  value       = aws_eks_cluster.main.endpoint
}

output "cluster_certificate_authority" {
  description = "Certificate Authority fuer kubectl Konfiguration"
  value       = aws_eks_cluster.main.certificate_authority[0].data
  sensitive   = true
}

output "cluster_security_group_id" {
  description = "ID der EKS Cluster Security Group"
  value       = aws_security_group.eks_cluster.id
}

output "node_security_group_id" {
  description = "ID der EKS Nodes Security Group"
  value       = aws_security_group.eks_nodes.id
}
