# Security Group
resource "aws_security_group" "immudb" {
  name        = "${var.project_name}-immudb-sg"
  description = "ImmuDB Security Group"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 3322
    to_port     = 3322
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  ingress {
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  ingress {
    from_port   = 9497
    to_port     = 9497
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
    Name = "${var.project_name}-immudb-sg"
  }
}

# IAM Role
resource "aws_iam_role" "immudb" {
  name = "${var.project_name}-immudb-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "immudb" {
  name = "${var.project_name}-immudb-policy"
  role = aws_iam_role.immudb.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
      Resource = ["${aws_s3_bucket.immudb.arn}", "${aws_s3_bucket.immudb.arn}/*"]
    }]
  })
}

resource "aws_iam_instance_profile" "immudb" {
  name = "${var.project_name}-immudb-profile"
  role = aws_iam_role.immudb.name
}

# S3 Bucket fuer ImmuDB Backups
resource "aws_s3_bucket" "immudb" {
  bucket        = "${var.project_name}-immudb-${var.environment}"
  force_destroy = true

  tags = {
    Name = "${var.project_name}-immudb"
  }
}

resource "aws_s3_bucket_versioning" "immudb" {
  bucket = aws_s3_bucket.immudb.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "immudb" {
  bucket = aws_s3_bucket.immudb.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "immudb" {
  bucket                  = aws_s3_bucket.immudb.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# EBS Volume
resource "aws_ebs_volume" "immudb" {
  availability_zone = data.aws_subnet.first.availability_zone
  size              = var.storage_gb
  type              = "gp3"

  tags = {
    Name = "${var.project_name}-immudb-data"
  }
}

data "aws_subnet" "first" {
  id = var.private_subnet_ids[0]
}

# EC2 Instance - t3.micro
resource "aws_instance" "immudb" {
  ami                    = var.ami_id
  instance_type          = "t3.micro"
  subnet_id              = var.private_subnet_ids[0]
  vpc_security_group_ids = [aws_security_group.immudb.id]
  iam_instance_profile   = aws_iam_instance_profile.immudb.name

  user_data = <<-USERDATA
    #!/bin/bash
    apt-get update -y
    apt-get install -y wget

    wget https://github.com/codenotary/immudb/releases/download/v1.9.5/immudb-v1.9.5-linux-amd64
    chmod +x immudb-v1.9.5-linux-amd64
    mv immudb-v1.9.5-linux-amd64 /usr/local/bin/immudb

    useradd -r -s /bin/false immudb
    mkdir -p /var/lib/immudb
    chown immudb:immudb /var/lib/immudb

    cat > /etc/systemd/system/immudb.service << 'SERVICE'
[Unit]
Description=ImmuDB
After=network.target

[Service]
User=immudb
ExecStart=/usr/local/bin/immudb
Restart=always

[Install]
WantedBy=multi-user.target
SERVICE

    systemctl enable immudb
    systemctl start immudb
  USERDATA

  tags = {
    Name = "${var.project_name}-immudb"
  }
}

resource "aws_volume_attachment" "immudb" {
  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.immudb.id
  instance_id = aws_instance.immudb.id
}
