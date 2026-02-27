output "vpc_id" {
  description = "ID des erstellten VPC"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "IDs der oeffentlichen Subnets"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "IDs der privaten Subnets"
  value       = aws_subnet.private[*].id
}
