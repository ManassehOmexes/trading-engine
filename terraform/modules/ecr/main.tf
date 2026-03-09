# ECR Repository fuer jeden Trading Service

locals {
  services = [
    "data-ingestion",
    "finbert",
    "indicator-service",
    "risk-manager",
    "order-executor",
    "telegram-bot"
  ]
}

resource "aws_ecr_repository" "services" {
  for_each = toset(local.services)

  name                 = "${var.project_name}-${var.environment}-${each.value}"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Name    = "${var.project_name}-${var.environment}-${each.value}"
    Service = each.value
  }
}

# Lifecycle Policy: Behalte nur die letzten 10 Images pro Repository
resource "aws_ecr_lifecycle_policy" "services" {
  for_each   = toset(local.services)
  repository = aws_ecr_repository.services[each.value].name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Behalte nur die letzten 10 Images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = {
        type = "expire"
      }
    }]
  })
}
