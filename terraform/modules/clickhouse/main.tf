# ─── BLOCK 1: Security Group ───────────────────────────────────────────────

resource "aws_security_group" "clickhouse" {
  name        = "${var.project_name}-${var.environment}-clickhouse-sg"
  description = "Security Group fuer ClickHouse"
  vpc_id      = var.vpc_id

  # HTTP Interface fuer Abfragen
  ingress {
    description = "ClickHouse HTTP"
    from_port   = 8123
    to_port     = 8123
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  # Native TCP Interface (schneller als HTTP)
  ingress {
    description = "ClickHouse Native TCP"
    from_port   = 9000
    to_port     = 9000
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-clickhouse-sg"
  }
}

# ─── BLOCK 2: IAM Role ─────────────────────────────────────────────────────
# ClickHouse EC2 Instanz braucht Zugriff auf S3 fuer Backups

resource "aws_iam_role" "clickhouse" {
  name = "${var.project_name}-${var.environment}-clickhouse-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })

  tags = {
    Name = "${var.project_name}-${var.environment}-clickhouse-role"
  }
}

resource "aws_iam_role_policy" "clickhouse" {
  name = "${var.project_name}-${var.environment}-clickhouse-policy"
  role = aws_iam_role.clickhouse.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ]
      Resource = [
        aws_s3_bucket.clickhouse_backup.arn,
        "${aws_s3_bucket.clickhouse_backup.arn}/*"
      ]
    }]
  })
}

resource "aws_iam_instance_profile" "clickhouse" {
  name = "${var.project_name}-${var.environment}-clickhouse-profile"
  role = aws_iam_role.clickhouse.name
}

# ─── BLOCK 3: S3 Backup Bucket ─────────────────────────────────────────────
# Taeglich automatisches Backup der ClickHouse Daten nach S3

resource "aws_s3_bucket" "clickhouse_backup" {
  bucket = "${var.project_name}-${var.environment}-clickhouse-backup"

  tags = {
    Name = "${var.project_name}-${var.environment}-clickhouse-backup"
  }
}

resource "aws_s3_bucket_versioning" "clickhouse_backup" {
  bucket = aws_s3_bucket.clickhouse_backup.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "clickhouse_backup" {
  bucket = aws_s3_bucket.clickhouse_backup.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "clickhouse_backup" {
  bucket                  = aws_s3_bucket.clickhouse_backup.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ─── BLOCK 4: EBS Volume ───────────────────────────────────────────────────
# Separates Volume fuer ClickHouse Daten (unabhaengig von der OS-Disk)

resource "aws_ebs_volume" "clickhouse_data" {
  availability_zone = "us-east-1a"
  size              = var.storage_gb
  type              = "gp3"
  encrypted         = true

  tags = {
    Name = "${var.project_name}-${var.environment}-clickhouse-data"
  }
}

# ─── BLOCK 5: EC2 Instanz ──────────────────────────────────────────────────

resource "aws_instance" "clickhouse" {
  ami                    = var.ami_id
  instance_type          = var.instance_type
  subnet_id              = var.private_subnet_ids[0]
  vpc_security_group_ids = [aws_security_group.clickhouse.id]
  iam_instance_profile   = aws_iam_instance_profile.clickhouse.name

  # Root Volume (OS)
  root_block_device {
    volume_size           = 20
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
  }

  # User Data: Installiert ClickHouse beim ersten Start automatisch
  user_data = <<-USERDATA
    #!/bin/bash
    set -e

    # System aktualisieren
    apt-get update -y

    # ClickHouse Repository hinzufuegen
    apt-get install -y apt-transport-https ca-certificates curl gnupg
    curl -fsSL 'https://packages.clickhouse.com/rpm/lts/repodata/repomd.xml.key' \
      | gpg --dearmor -o /usr/share/keyrings/clickhouse-keyring.gpg
    echo "deb [signed-by=/usr/share/keyrings/clickhouse-keyring.gpg] \
      https://packages.clickhouse.com/deb stable main" \
      | tee /etc/apt/sources.list.d/clickhouse.list

    # ClickHouse installieren
    apt-get update -y
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
      clickhouse-server clickhouse-client

    # ClickHouse starten und beim Boot aktivieren
    systemctl enable clickhouse-server
    systemctl start clickhouse-server

    echo "ClickHouse installation complete" > /var/log/clickhouse-install.log
  USERDATA

  tags = {
    Name = "${var.project_name}-${var.environment}-clickhouse"
  }
}

# EBS Volume an EC2 Instanz anhaengen
resource "aws_volume_attachment" "clickhouse_data" {
  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.clickhouse_data.id
  instance_id = aws_instance.clickhouse.id
}
