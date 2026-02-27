# ─── BLOCK 1: Security Group ───────────────────────────────────────────────
# Definiert welcher Netzwerkverkehr zu Vault erlaubt ist

resource "aws_security_group" "vault" {
  name        = "${var.project_name}-${var.environment}-vault-sg"
  description = "Security Group fuer HashiCorp Vault"
  vpc_id      = var.vpc_id

  # Eingehend: Vault API nur aus dem VPC erreichbar
  ingress {
    description = "Vault API"
    from_port   = 8200
    to_port     = 8200
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  # Eingehend: Vault Cluster-Kommunikation (fuer spaetere HA-Konfiguration)
  ingress {
    description = "Vault Cluster"
    from_port   = 8201
    to_port     = 8201
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  # Ausgehend: Alles erlaubt (fuer Updates, AWS API Calls)
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-vault-sg"
  }
}

# ─── BLOCK 2: IAM Role ─────────────────────────────────────────────────────
# Gibt Vault die Berechtigung mit AWS Services zu kommunizieren

resource "aws_iam_role" "vault" {
  name = "${var.project_name}-${var.environment}-vault-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-${var.environment}-vault-role"
  }
}

resource "aws_iam_role_policy" "vault" {
  name = "${var.project_name}-${var.environment}-vault-policy"
  role = aws_iam_role.vault.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Vault darf seinen eigenen verschluesselten Storage in S3 verwalten
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.vault_storage.arn,
          "${aws_s3_bucket.vault_storage.arn}/*"
        ]
      },
      {
        # Vault darf KMS nutzen um seinen Master-Key zu verschluesseln
        Effect = "Allow"
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = aws_kms_key.vault.arn
      }
    ]
  })
}

resource "aws_iam_instance_profile" "vault" {
  name = "${var.project_name}-${var.environment}-vault-profile"
  role = aws_iam_role.vault.name
}

# ─── BLOCK 3: KMS + S3 Storage ─────────────────────────────────────────────
# KMS: AWS Key Management Service verschluesselt den Vault Master-Key
# S3:  Vault speichert seine verschluesselten Daten in S3 (kein lokaler State)

resource "aws_kms_key" "vault" {
  description             = "KMS Key fuer Vault Auto-Unseal"
  deletion_window_in_days = 10
  enable_key_rotation     = true

  tags = {
    Name = "${var.project_name}-${var.environment}-vault-kms"
  }
}

resource "aws_kms_alias" "vault" {
  name          = "alias/${var.project_name}-${var.environment}-vault"
  target_key_id = aws_kms_key.vault.key_id
}

resource "aws_s3_bucket" "vault_storage" {
  bucket = "${var.project_name}-${var.environment}-vault-storage"

  tags = {
    Name = "${var.project_name}-${var.environment}-vault-storage"
  }
}

resource "aws_s3_bucket_versioning" "vault_storage" {
  bucket = aws_s3_bucket.vault_storage.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "vault_storage" {
  bucket = aws_s3_bucket.vault_storage.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.vault.arn
    }
  }
}

resource "aws_s3_bucket_public_access_block" "vault_storage" {
  bucket = aws_s3_bucket.vault_storage.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
