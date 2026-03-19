# Vault Policy fuer die Trading Engine
# Gibt den Services Lesezugriff auf ihre Secrets

# Alpaca Credentials (nur data-ingestion und order-executor)
path "secret/data/trading-engine/alpaca" {
  capabilities = ["read"]
}

# Kafka Credentials (alle Services)
path "secret/data/trading-engine/kafka" {
  capabilities = ["read"]
}

# ClickHouse Credentials (finbert, indicator-service)
path "secret/data/trading-engine/clickhouse" {
  capabilities = ["read"]
}

# Telegram Credentials (nur telegram-bot)
path "secret/data/trading-engine/telegram" {
  capabilities = ["read"]
}
