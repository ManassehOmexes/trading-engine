[1mdiff --git a/terraform/environments/dev/main.tf b/terraform/environments/dev/main.tf[m
[1mindex b35b9f8..8fc97fe 100644[m
[1m--- a/terraform/environments/dev/main.tf[m
[1m+++ b/terraform/environments/dev/main.tf[m
[36m@@ -46,8 +46,8 @@[m [mmodule "immudb" {[m
 }[m
 [m
 module "eks" {[m
[31m-  source             = "../../modules/eks"[m
[31m-  [m
[32m+[m[32m  source = "../../modules/eks"[m
[32m+[m
   project_name       = "trading-engine"[m
   environment        = "dev"[m
   vpc_id             = module.vpc.vpc_id[m
[1mdiff --git a/terraform/modules/clickhouse/main.tf b/terraform/modules/clickhouse/main.tf[m
[1mindex 135f364..5ceeca4 100644[m
[1m--- a/terraform/modules/clickhouse/main.tf[m
[1m+++ b/terraform/modules/clickhouse/main.tf[m
[36m@@ -65,7 +65,7 @@[m [mresource "aws_iam_instance_profile" "clickhouse" {[m
 resource "aws_s3_bucket" "clickhouse" {[m
   bucket        = "${var.project_name}-clickhouse-${var.environment}"[m
   force_destroy = true[m
[31m-  tags = { Name = "${var.project_name}-clickhouse" }[m
[32m+[m[32m  tags          = { Name = "${var.project_name}-clickhouse" }[m
 }[m
 [m
 resource "aws_s3_bucket_versioning" "clickhouse" {[m
[36m@@ -96,7 +96,7 @@[m [mresource "aws_ebs_volume" "clickhouse" {[m
   availability_zone = data.aws_subnet.first.availability_zone[m
   size              = var.storage_gb[m
   type              = "gp3"[m
[31m-  tags = { Name = "${var.project_name}-clickhouse-data" }[m
[32m+[m[32m  tags              = { Name = "${var.project_name}-clickhouse-data" }[m
 }[m
 [m
 resource "aws_instance" "clickhouse" {[m
[1mdiff --git a/terraform/modules/ecr/main.tf b/terraform/modules/ecr/main.tf[m
[1mindex 6634987..56e5935 100644[m
[1m--- a/terraform/modules/ecr/main.tf[m
[1m+++ b/terraform/modules/ecr/main.tf[m
[36m@@ -16,6 +16,7 @@[m [mresource "aws_ecr_repository" "services" {[m
 [m
   name                 = "${var.project_name}-${var.environment}-${each.value}"[m
   image_tag_mutability = "IMMUTABLE"[m
[32m+[m[32m  force_delete         = true[m
 [m
   image_scanning_configuration {[m
     scan_on_push = true[m
[1mdiff --git a/terraform/modules/eks/variables.tf b/terraform/modules/eks/variables.tf[m
[1mindex 183e8ad..22c9a50 100644[m
[1m--- a/terraform/modules/eks/variables.tf[m
[1m+++ b/terraform/modules/eks/variables.tf[m
[36m@@ -32,7 +32,7 @@[m [mvariable "kubernetes_version" {[m
 variable "node_instance_type" {[m
   description = "EC2 Instance Typ fuer Kubernetes Worker Nodes"[m
   type        = string[m
[31m-  default     = "t3.medium"[m
[32m+[m[32m  default     = "t3.small"[m
 }[m
 [m
 variable "node_min_size" {[m
[1mdiff --git a/terraform/modules/immudb/main.tf b/terraform/modules/immudb/main.tf[m
[1mindex d3b33ca..a9c6d79 100644[m
[1m--- a/terraform/modules/immudb/main.tf[m
[1m+++ b/terraform/modules/immudb/main.tf[m
[36m@@ -69,7 +69,7 @@[m [mresource "aws_iam_instance_profile" "immudb" {[m
 resource "aws_s3_bucket" "immudb" {[m
   bucket        = "${var.project_name}-immudb-${var.environment}"[m
   force_destroy = true[m
[31m-  tags = { Name = "${var.project_name}-immudb" }[m
[32m+[m[32m  tags          = { Name = "${var.project_name}-immudb" }[m
 }[m
 [m
 resource "aws_s3_bucket_versioning" "immudb" {[m
[36m@@ -100,7 +100,7 @@[m [mresource "aws_ebs_volume" "immudb" {[m
   availability_zone = data.aws_subnet.first.availability_zone[m
   size              = var.storage_gb[m
   type              = "gp3"[m
[31m-  tags = { Name = "${var.project_name}-immudb-data" }[m
[32m+[m[32m  tags              = { Name = "${var.project_name}-immudb-data" }[m
 }[m
 [m
 resource "aws_instance" "immudb" {[m
[1mdiff --git a/terraform/modules/kafka/main.tf b/terraform/modules/kafka/main.tf[m
[1mindex c15d804..2f0763a 100644[m
[1m--- a/terraform/modules/kafka/main.tf[m
[1m+++ b/terraform/modules/kafka/main.tf[m
[36m@@ -47,8 +47,8 @@[m [mresource "aws_security_group" "msk" {[m
 # ─── BLOCK 2: MSK Konfiguration ────────────────────────────────────────────[m
 [m
 resource "aws_msk_configuration" "main" {[m
[31m-  name              = "${var.project_name}-${var.environment}-msk-config"[m
[31m-  kafka_versions    = [var.kafka_version][m
[32m+[m[32m  name           = "${var.project_name}-${var.environment}-msk-config"[m
[32m+[m[32m  kafka_versions = [var.kafka_version][m
 [m
   server_properties = <<PROPERTIES[m
 # Nachrichten werden 7 Tage gespeichert (604800000 ms)[m
