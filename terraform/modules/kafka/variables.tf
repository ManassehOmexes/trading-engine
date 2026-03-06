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
  description = "IDs der Private Subnets fuer MSK"
  type        = list(string)
}

variable "allowed_cidr_blocks" {
  description = "CIDR Bloecke die auf MSK zugreifen duerfen"
  type        = list(string)
  default     = ["10.0.0.0/16"]
}

variable "kafka_version" {
  description = "Apache Kafka Version"
  type        = string
  default     = "3.5.1"
}

variable "broker_instance_type" {
  description = "EC2 Instance Typ fuer Kafka Broker"
  type        = string
  default     = "kafka.t3.small"
}

variable "broker_storage_gb" {
  description = "Storage pro Broker in GB"
  type        = number
  default     = 20
}
