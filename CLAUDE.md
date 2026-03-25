# Trading Engine — Claude Code Context

## Projekt
Autonome algorithmische Trading Engine für US-Aktien auf AWS.
Privat, kein BaFin/MiFID II Track erforderlich.

## Mein Level
- Wirtschaftsinformatiker, DataOps Spezialisierung (Einsteiger-Praxis)
- Stark: Python, SQL, Terraform, AWS, Kafka, Spark
- Lerne gerade: Airflow, dbt, DataOps Best Practices
- Erkläre neue Konzepte immer kurz, nicht nur Code liefern
- Bei Architektur-Entscheidungen: 2 Optionen + Empfehlung zeigen

## Stack
- Cloud: AWS (us-east-1), EKS, MSK (Kafka), EC2 (ClickHouse, ImmuDB, Vault)
- IaC: Terraform >= 1.7, Remote State in S3, Lock in DynamoDB
- Container: Docker, ECR, Kubernetes (Helm)
- CI/CD: GitHub Actions
- Sprachen: Python 3.13, HCL

## Konventionen

### Python
- Type hints auf allen Funktionen
- Docstrings auf allen Klassen und öffentlichen Funktionen
- Error handling mit expliziten Exception-Typen (kein blankes `except:`)
- Umgebungsvariablen ausschließlich via `os.environ[]` (wirft KeyError wenn fehlend — gewollt)
- Kein `os.getenv()` (gibt None zurück und versteckt Fehler)

### Terraform
- Remote State in S3, Lock in DynamoDB
- `common_tags` auf allen Ressourcen
- `force_destroy = true` auf allen S3 Buckets

## Projektstruktur
```
trading-engine/
├── terraform/
│   ├── environments/dev/     # Terraform Backend + Modul-Aufrufe
│   └── modules/              # vpc, vault, kafka, clickhouse, immudb, eks, ecr
├── src/
│   ├── data-ingestion/       # Alpaca WebSocket → Kafka
│   ├── finbert/              # FinBERT Sentiment-Analyse
│   ├── indicator-service/    # RSI, MACD, BB, VWAP, ATR, Pivot
│   ├── signal-aggregator/    # Kombiniert Indikator + Sentiment
│   ├── risk-manager/         # Half Kelly, ATR Stop-Loss, Guardian
│   ├── order-executor/       # Alpaca Paper/Live Trading
│   └── telegram-bot/         # Alert + One-Click Approve
├── helm/
│   ├── trading-service/      # Gemeinsames Helm Chart Template
│   └── values/               # Service-spezifische Werte
├── kubernetes/
│   ├── namespaces/
│   └── rbac/
├── clickhouse/
│   └── schema.sql            # 7 bitemporale Tabellen
└── .github/workflows/        # Terraform + Docker Build Pipelines
```

## Kritische Regeln
- NIEMALS Secrets in Code oder Git. Alle Credentials via Vault oder Kubernetes Secrets.
- IMMER `terraform plan` vor `terraform apply`.
- Terraform Apply und Destroy NUR via GitHub Actions (keine lokalen Runs wegen Netzwerkabbrüchen).
- Alle Datenpunkte sind bitemporal: `valid_time` + `transaction_time` auf jeder Zeile.
- Paper Trading Default: `PAPER_TRADING=true`. Live nur wenn explizit gesetzt.

## Was ich NICHT will
- Keine überkomplexen Lösungen für ein Portfolio-Projekt
- Keine Libraries außerhalb des definierten Stacks
- Immer erklären WARUM, nicht nur WAS

## Aktuelle Prioritäten
- ClickHouse Schema vervollständigen (4 fehlende Tabellen: market_ticks, market_bars, sentiment_results, indicator_results)
- force_destroy = true auf alle S3 Buckets in allen Terraform Modulen
- indicator-service und signal-aggregator deployen
- ImmuDB Setup prüfen

## Commit Konvention
Format: `typ: kurze beschreibung`
Typen: feat, fix, chore, docs, ci

## Tests
Jeder Service hat eigene Tests in `src/<service>/tests/`.
Ausführen: `cd src/<service> && python -m pytest`

## Kubernetes Namespaces
- data-ingestion: Data Ingestion Service
- ml-services: FinBERT, Indicator Service
- trading: Risk Manager, Order Executor
- notifications: Telegram Bot
- monitoring: Prometheus, Grafana (noch nicht deployed)

## Wichtige Adressen (nur nach terraform apply gültig)
- Vault EC2: Port 8200, SSM-fähig
- ClickHouse EC2: Port 9000, SSM-fähig
- ImmuDB EC2: Port 3322, SSM-fähig
- MSK Kafka: Bootstrap URL aus `aws kafka get-bootstrap-brokers`

## Bekannte Probleme und Lösungen
- FinBERT: Memory Limit 2048Mi, Request 768Mi, benötigt 3 EKS Nodes (t3.small)
- SSM Agent in user_data: snap install funktioniert nicht beim ersten Boot → manuelle Installation via SSM nötig
- Kubernetes Secrets werden bei terraform destroy gelöscht → beim nächsten Login neu erstellen
- S3 Buckets mit Versionierung: vor destroy manuell leeren oder force_destroy = true setzen
- terraform apply NUR via GitHub Actions (lokale Runs brechen bei MSK wegen ~15min Erstellungszeit ab)
