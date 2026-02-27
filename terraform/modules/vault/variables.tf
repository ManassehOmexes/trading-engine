variable "project_name" {
  description = "Name des Projekts"
  type        = string
}

variable "environment" {
  description = "Umgebung: dev oder prod"
  type        = string
}

variable "vpc_id" {
  description = "ID des VPC in dem Vault laeuft"
  type        = string
}

variable "private_subnet_ids" {
  description = "IDs der Private Subnets fuer Vault"
  type        = list(string)
}

variable "allowed_cidr_blocks" {
  description = "CIDR Bloecke die auf Vault zugreifen duerfen"
  type        = list(string)
  default     = ["10.0.0.0/16"]
}
