module "vpc" {
  source = "../../modules/vpc"

  project_name         = "trading-engine"
  environment          = "dev"
  vpc_cidr             = "10.0.0.0/16"
  availability_zones   = ["us-east-1a", "us-east-1b"]
  public_subnet_cidrs  = ["10.0.1.0/24", "10.0.2.0/24"]
  private_subnet_cidrs = ["10.0.11.0/24", "10.0.12.0/24"]
}

module "vault" {
  source = "../../modules/vault"

  project_name       = "trading-engine"
  environment        = "dev"
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
}

module "kafka" {
  source = "../../modules/kafka"

  project_name       = "trading-engine"
  environment        = "dev"
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
}

module "clickhouse" {
  source = "../../modules/clickhouse"

  project_name       = "trading-engine"
  environment        = "dev"
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
}

module "immudb" {
  source = "../../modules/immudb"

  project_name       = "trading-engine"
  environment        = "dev"
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
}

module "eks" {
  source = "../../modules/eks"

  project_name       = "trading-engine"
  environment        = "dev"
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  public_subnet_ids  = module.vpc.public_subnet_ids
  node_instance_type = "t3.small"
}

module "ecr" {
  source = "../../modules/ecr"

  project_name = "trading-engine"
  environment  = "dev"
}
