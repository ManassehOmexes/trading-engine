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
  description = "IDs der Private Subnets fuer EKS"
  type        = list(string)
}

variable "public_subnet_ids" {
  description = "IDs der Public Subnets fuer Load Balancer"
  type        = list(string)
}

variable "kubernetes_version" {
  description = "Kubernetes Version"
  type        = string
  default     = "1.31"
}

variable "node_instance_type" {
  description = "EC2 Instance Typ fuer Kubernetes Worker Nodes"
  type        = string
  default     = "t3.medium"
}

variable "node_min_size" {
  description = "Minimale Anzahl Worker Nodes"
  type        = number
  default     = 1
}

variable "node_max_size" {
  description = "Maximale Anzahl Worker Nodes (Autoscaling)"
  type        = number
  default     = 4
}

variable "node_desired_size" {
  description = "Gewuenschte Anzahl Worker Nodes im Normalbetrieb"
  type        = number
  default     = 2
}
