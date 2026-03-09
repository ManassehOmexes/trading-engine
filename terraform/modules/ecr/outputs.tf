output "repository_urls" {
  description = "URLs aller ECR Repositories"
  value = {
    for service, repo in aws_ecr_repository.services :
    service => repo.repository_url
  }
}
