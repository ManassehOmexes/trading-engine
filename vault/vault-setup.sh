#!/bin/bash
# Vault Setup Script
# Wird einmalig nach terraform apply ausgefuehrt
# Setzt Secrets und Kubernetes Auth Methode auf

set -e

VAULT_ADDR=${VAULT_ADDR:-"http://localhost:8200"}
CLUSTER_NAME="trading-engine-dev"
REGION="us-east-1"

echo "==> Vault Adresse: $VAULT_ADDR"

# 1. Kubernetes Auth Methode aktivieren
echo "==> Aktiviere Kubernetes Auth..."
vault auth enable kubernetes || echo "Bereits aktiviert"

# 2. Kubernetes Auth konfigurieren
echo "==> Konfiguriere Kubernetes Auth..."
vault write auth/kubernetes/config \
  kubernetes_host="$(kubectl config view --raw -o jsonpath='{.clusters[0].cluster.server}')" \
  kubernetes_ca_cert="$(kubectl config view --raw -o jsonpath='{.clusters[0].cluster.certificate-authority-data}' | base64 -d)"

# 3. Policy erstellen
echo "==> Erstelle Vault Policy..."
vault policy write trading-engine-policy vault-policy.hcl

# 4. Kubernetes Role erstellen
echo "==> Erstelle Kubernetes Role..."
vault write auth/kubernetes/role/trading-engine-role \
  bound_service_account_names="data-ingestion-sa,finbert-sa,indicator-sa,risk-manager-sa,order-executor-sa,telegram-bot-sa,signal-aggregator-sa" \
  bound_service_account_namespaces="trading,ml-services,notifications" \
  policies="trading-engine-policy" \
  ttl="1h"

# 5. KV Secrets Engine aktivieren
echo "==> Aktiviere KV Secrets Engine..."
vault secrets enable -path=secret kv-v2 || echo "Bereits aktiviert"

# 6. Platzhalter Secrets setzen
# ACHTUNG: Echte Werte hier eintragen bevor das System gestartet wird
echo "==> Setze Secret Platzhalter..."

vault kv put secret/trading-engine/alpaca \
  api_key="DEIN_ALPACA_API_KEY" \
  secret_key="DEIN_ALPACA_SECRET_KEY"

vault kv put secret/trading-engine/kafka \
  bootstrap_servers="DEIN_MSK_BOOTSTRAP_SERVER:9092"

vault kv put secret/trading-engine/clickhouse \
  host="DEINE_CLICKHOUSE_EC2_IP" \
  port="8123" \
  user="default" \
  password="DEIN_CLICKHOUSE_PASSWORD"

vault kv put secret/trading-engine/telegram \
  token="DEIN_TELEGRAM_BOT_TOKEN" \
  chat_id="DEINE_TELEGRAM_CHAT_ID"

echo ""
echo "==> Vault Setup abgeschlossen."
echo "==> WICHTIG: Ersetze die Platzhalter mit echten Werten:"
echo "    vault kv put secret/trading-engine/alpaca api_key=... secret_key=..."
echo "    vault kv put secret/trading-engine/telegram token=... chat_id=..."
