# Security Group
resource "aws_security_group" "clickhouse" {
  name        = "${var.project_name}-clickhouse-sg"
  description = "ClickHouse Security Group"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 8123
    to_port     = 8123
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  ingress {
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
    Name = "${var.project_name}-clickhouse-sg"
  }
}

# IAM Role
resource "aws_iam_role" "clickhouse" {
  name = "${var.project_name}-clickhouse-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "clickhouse" {
  name = "${var.project_name}-clickhouse-policy"
  role = aws_iam_role.clickhouse.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
      Resource = ["${aws_s3_bucket.clickhouse.arn}", "${aws_s3_bucket.clickhouse.arn}/*"]
    }]
  })
}

resource "aws_iam_instance_profile" "clickhouse" {
  name = "${var.project_name}-clickhouse-profile"
  role = aws_iam_role.clickhouse.name
}

# S3 Bucket fuer ClickHouse Backups
resource "aws_s3_bucket" "clickhouse" {
  bucket        = "${var.project_name}-clickhouse-${var.environment}"
  force_destroy = true

  tags = {
    Name = "${var.project_name}-clickhouse"
  }
}

resource "aws_s3_bucket_versioning" "clickhouse" {
  bucket = aws_s3_bucket.clickhouse.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "clickhouse" {
  bucket = aws_s3_bucket.clickhouse.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "clickhouse" {
  bucket                  = aws_s3_bucket.clickhouse.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# EBS Volume
resource "aws_ebs_volume" "clickhouse" {
  availability_zone = var.private_subnet_ids[0] == "" ? "us-east-1a" : data.aws_subnet.first.availability_zone
  size              = var.storage_gb
  type              = "gp3"

  tags = {
    Name = "${var.project_name}-clickhouse-data"
  }
}

data "aws_subnet" "first" {
  id = var.private_subnet_ids[0]
}

# EC2 Instance - t3.small
resource "aws_instance" "clickhouse" {
  ami                    = var.ami_id
  instance_type          = "t3.small"
  subnet_id              = var.private_subnet_ids[0]
  vpc_security_group_ids = [aws_security_group.clickhouse.id]
  iam_instance_profile   = aws_iam_instance_profile.clickhouse.name

  user_data = <<-USERDATA
    #!/bin/bash
    apt-get update -y
    apt-get install -y apt-transport-https ca-certificates curl gnupg

    curl -fsSL 'https://packages.clickhouse.com/rpm/lts/repodata/repomd.xml.key' | gpg --dearmor -o /usr/share/keyrings/clickhouse-keyring.gpg
    echo "deb [signed-by=/usr/share/keyrings/clickhouse-keyring.gpg] https://packages.clickhouse.com/deb stable main" | tee /etc/apt/sources.list.d/clickhouse.list
    apt-get update -y
    apt-get install -y clickhouse-server clickhouse-client

    systemctl enable clickhouse-server
    systemctl start clickhouse-server
  USERDATA

  tags = {
    Name = "${var.project_name}-clickhouse"
  }
}

resource "aws_volume_attachment" "clickhouse" {
  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.clickhouse.id
  instance_id = aws_instance.clickhouse.id
}
