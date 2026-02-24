terraform {
  backend "s3" {
    bucket         = "trading-engine-tfstate-dev"
    key            = "dev/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "trading-engine-tfstate-lock"
  }
}
