variable "project_name" {
  description = "Name des Projekts"
  type        = string
}

variable "environment" {
  description = "Umgebung: dev oder prod"
  type        = string
}

variable "vpc_id" {
  description = "ID des VPC"
  type        = string
}

variable "private_subnet_ids" {
  description = "IDs der Private Subnets fuer ClickHouse"
  type        = list(string)
}

variable "allowed_cidr_blocks" {
  description = "CIDR Blöcke die auf ClickHouse zugreifen duerfen"
  type        = list(string)
  default     = ["10.0.0.0/16"]
}

variable "instance_type" {
  description = "EC2 Instance Typ fuer ClickHouse"
  type        = string
  default     = "t3.medium"
}

variable "storage_gb" {
  description = "EBS Storage für ClickHouse Daten in GB"
  type        = number
  default     = 100
}

variable "ami_id" {
  description = "Amazon Machine Image ID (Ubuntu 22.04 LTS)"
  type        = string
  default     = "ami-0c7217cdde317cfec"
}
