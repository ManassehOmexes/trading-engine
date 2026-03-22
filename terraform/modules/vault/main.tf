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
          "kms:GenerateDataKey",
          "kms:DescribeKey"
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

# EC2 Instance fuer Vault
data "aws_subnet" "vault_first" {
  id = var.private_subnet_ids[0]
}

resource "aws_instance" "vault" {
  ami                    = var.ami_id
  instance_type          = "t3.micro"
  subnet_id              = var.private_subnet_ids[0]
  vpc_security_group_ids = [aws_security_group.vault.id]
  iam_instance_profile   = aws_iam_instance_profile.vault.name

  user_data = <<-USERDATA
    #!/bin/bash
    apt-get update -y
    apt-get install -y wget unzip snapd
    snap install amazon-ssm-agent --classic
    systemctl enable snap.amazon-ssm-agent.amazon-ssm-agent.service
    systemctl start snap.amazon-ssm-agent.amazon-ssm-agent.service

    wget https://releases.hashicorp.com/vault/1.15.4/vault_1.15.4_linux_amd64.zip
    unzip vault_1.15.4_linux_amd64.zip
    mv vault /usr/local/bin/
    chmod +x /usr/local/bin/vault

    useradd -r -s /bin/false vault
    mkdir -p /etc/vault /opt/vault/data
    chown vault:vault /opt/vault/data

    cat > /etc/vault/vault.hcl << 'CONFIG'
ui = true

storage "file" {
  path = "/opt/vault/data"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = true
}

seal "awskms" {
  region     = "us-east-1"
  kms_key_id = "${aws_kms_key.vault.key_id}"
}
CONFIG

    cat > /etc/systemd/system/vault.service << 'SERVICE'
[Unit]
Description=HashiCorp Vault
After=network.target

[Service]
User=vault
ExecStart=/usr/local/bin/vault server -config=/etc/vault/vault.hcl
Restart=always
Environment=VAULT_ADDR=http://127.0.0.1:8200

[Install]
WantedBy=multi-user.target
SERVICE

    systemctl enable vault
    systemctl start vault
  USERDATA

  tags = {
    Name = "${var.project_name}-vault"
  }
}

resource "aws_iam_role_policy_attachment" "vault_ssm" {
  role       = aws_iam_role.vault.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}
