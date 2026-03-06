# ─── BLOCK 1: Security Group ───────────────────────────────────────────────

resource "aws_security_group" "immudb" {
  name        = "${var.project_name}-${var.environment}-immudb-sg"
  description = "Security Group fuer ImmuDB"
  vpc_id      = var.vpc_id

  ingress {
    description = "ImmuDB gRPC"
    from_port   = 3322
    to_port     = 3322
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  ingress {
    description = "ImmuDB REST"
    from_port   = 8080
    to_port     = 8080
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
    Name = "${var.project_name}-${var.environment}-immudb-sg"
  }
}

# ─── BLOCK 2: IAM Role ─────────────────────────────────────────────────────

resource "aws_iam_role" "immudb" {
  name = "${var.project_name}-${var.environment}-immudb-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })

  tags = {
    Name = "${var.project_name}-${var.environment}-immudb-role"
  }
}

resource "aws_iam_role_policy" "immudb" {
  name = "${var.project_name}-${var.environment}-immudb-policy"
  role = aws_iam_role.immudb.id

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
        aws_s3_bucket.immudb_backup.arn,
        "${aws_s3_bucket.immudb_backup.arn}/*"
      ]
    }]
  })
}

resource "aws_iam_instance_profile" "immudb" {
  name = "${var.project_name}-${var.environment}-immudb-profile"
  role = aws_iam_role.immudb.name
}

# ─── BLOCK 3: S3 Backup Bucket ─────────────────────────────────────────────

resource "aws_s3_bucket" "immudb_backup" {
  bucket = "${var.project_name}-${var.environment}-immudb-backup"

  tags = {
    Name = "${var.project_name}-${var.environment}-immudb-backup"
  }
}

resource "aws_s3_bucket_versioning" "immudb_backup" {
  bucket = aws_s3_bucket.immudb_backup.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "immudb_backup" {
  bucket = aws_s3_bucket.immudb_backup.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "immudb_backup" {
  bucket                  = aws_s3_bucket.immudb_backup.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ─── BLOCK 4: EBS Volume ───────────────────────────────────────────────────

resource "aws_ebs_volume" "immudb_data" {
  availability_zone = "us-east-1a"
  size              = var.storage_gb
  type              = "gp3"
  encrypted         = true

  tags = {
    Name = "${var.project_name}-${var.environment}-immudb-data"
  }
}

# ─── BLOCK 5: EC2 Instanz ──────────────────────────────────────────────────

resource "aws_instance" "immudb" {
  ami                    = var.ami_id
  instance_type          = var.instance_type
  subnet_id              = var.private_subnet_ids[0]
  vpc_security_group_ids = [aws_security_group.immudb.id]
  iam_instance_profile   = aws_iam_instance_profile.immudb.name

  root_block_device {
    volume_size           = 20
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
  }

  user_data = <<-USERDATA
    #!/bin/bash
    set -e
    apt-get update -y
    apt-get install -y wget

    wget -O /usr/local/bin/immudb \
      "https://github.com/codenotary/immudb/releases/download/v1.9.5/immudb-v1.9.5-linux-amd64"
    chmod +x /usr/local/bin/immudb

    cat > /etc/systemd/system/immudb.service << 'SERVICE'
[Unit]
Description=ImmuDB - Immutable Database
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/immudb \
  --dir /data/immudb \
  --address 0.0.0.0 \
  --port 3322 \
  --metrics-server \
  --metrics-server-port 9497
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

    mkdir -p /data/immudb
    systemctl daemon-reload
    systemctl enable immudb
    systemctl start immudb
    echo "ImmuDB installation complete" > /var/log/immudb-install.log
  USERDATA

  tags = {
    Name = "${var.project_name}-${var.environment}-immudb"
  }
}

resource "aws_volume_attachment" "immudb_data" {
  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.immudb_data.id
  instance_id = aws_instance.immudb.id
}
