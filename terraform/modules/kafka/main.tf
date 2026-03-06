# ─── BLOCK 1: Security Group ───────────────────────────────────────────────

resource "aws_security_group" "msk" {
  name        = "${var.project_name}-${var.environment}-msk-sg"
  description = "Security Group fuer Amazon MSK (Kafka)"
  vpc_id      = var.vpc_id

  # Eingehend: Kafka Plaintext (intern, wird spaeter auf TLS umgestellt)
  ingress {
    description = "Kafka Plaintext"
    from_port   = 9092
    to_port     = 9092
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  # Eingehend: Kafka TLS
  ingress {
    description = "Kafka TLS"
    from_port   = 9094
    to_port     = 9094
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  # Eingehend: Zookeeper (interne Kafka-Koordination)
  ingress {
    description = "Zookeeper"
    from_port   = 2181
    to_port     = 2181
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
    Name = "${var.project_name}-${var.environment}-msk-sg"
  }
}

# ─── BLOCK 2: MSK Konfiguration ────────────────────────────────────────────

resource "aws_msk_configuration" "main" {
  name              = "${var.project_name}-${var.environment}-msk-config"
  kafka_versions    = [var.kafka_version]

  server_properties = <<PROPERTIES
# Nachrichten werden 7 Tage gespeichert (604800000 ms)
log.retention.ms=604800000

# Maximale Nachrichtengroesse: 10MB (fuer News-Artikel)
message.max.bytes=10485760

# Automatische Topic-Erstellung erlaubt
auto.create.topics.enable=true

# Replikationsfaktor fuer neue Topics
default.replication.factor=2

# Minimale In-Sync Replicas (Datensicherheit)
min.insync.replicas=1
PROPERTIES
}

# ─── BLOCK 3: MSK Cluster ──────────────────────────────────────────────────

resource "aws_msk_cluster" "main" {
  cluster_name           = "${var.project_name}-${var.environment}-kafka"
  kafka_version          = var.kafka_version
  number_of_broker_nodes = 2

  broker_node_group_info {
    instance_type   = var.broker_instance_type
    client_subnets  = var.private_subnet_ids
    security_groups = [aws_security_group.msk.id]

    storage_info {
      ebs_storage_info {
        volume_size = var.broker_storage_gb
      }
    }
  }

  configuration_info {
    arn      = aws_msk_configuration.main.arn
    revision = aws_msk_configuration.main.latest_revision
  }

  # Verschluesselung im Transit zwischen Clients und Brokern
  encryption_info {
    encryption_in_transit {
      client_broker = "TLS_PLAINTEXT"
      in_cluster    = true
    }
  }

  # Monitoring fuer Grafana Dashboard (Phase 6)
  open_monitoring {
    prometheus {
      jmx_exporter {
        enabled_in_broker = true
      }
      node_exporter {
        enabled_in_broker = true
      }
    }
  }

  # Logging nach CloudWatch
  logging_info {
    broker_logs {
      cloudwatch_logs {
        enabled   = true
        log_group = "/aws/msk/${var.project_name}-${var.environment}"
      }
    }
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-kafka"
  }
}

# ─── BLOCK 4: CloudWatch Log Group ─────────────────────────────────────────

resource "aws_cloudwatch_log_group" "msk" {
  name              = "/aws/msk/${var.project_name}-${var.environment}"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-${var.environment}-msk-logs"
  }
}
