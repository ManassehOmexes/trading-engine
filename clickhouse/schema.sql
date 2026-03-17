-- ClickHouse Schema fuer Trading Engine
-- Engine: ReplacingMergeTree fuer Deduplizierung
-- Bitemporal: valid_time + transaction_time in jeder Tabelle

-- ─────────────────────────────────────────────
-- 1. Market Ticks (Raw Trades von Alpaca)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS market_ticks
(
    symbol           String,
    price            Float64,
    size             Float64,
    exchange         String,
    valid_time       DateTime64(3, 'UTC'),   -- Wann der Trade an der Boerse stattfand
    transaction_time DateTime64(3, 'UTC'),   -- Wann wir ihn empfangen haben
    _inserted_at     DateTime64(3, 'UTC') DEFAULT now64()
)
ENGINE = ReplacingMergeTree(_inserted_at)
PARTITION BY toYYYYMM(valid_time)
ORDER BY (symbol, valid_time)
TTL valid_time + INTERVAL 90 DAY;

-- ─────────────────────────────────────────────
-- 2. Market Bars (1-Minuten OHLCV von Alpaca)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS market_bars
(
    symbol           String,
    open             Float64,
    high             Float64,
    low              Float64,
    close            Float64,
    volume           Float64,
    vwap             Nullable(Float64),
    valid_time       DateTime64(3, 'UTC'),
    transaction_time DateTime64(3, 'UTC'),
    _inserted_at     DateTime64(3, 'UTC') DEFAULT now64()
)
ENGINE = ReplacingMergeTree(_inserted_at)
PARTITION BY toYYYYMM(valid_time)
ORDER BY (symbol, valid_time)
TTL valid_time + INTERVAL 365 DAY;

-- ─────────────────────────────────────────────
-- 3. Sentiment Results (FinBERT Output)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sentiment_results
(
    symbol           String,
    headline         String,
    sentiment_score  Float64,             -- P(positive) - P(negative), -1 bis +1
    sentiment_signal String,             -- BUY / SELL / HOLD
    positive         Float64,
    negative         Float64,
    neutral          Float64,
    model            String,
    valid_time       DateTime64(3, 'UTC'),
    transaction_time DateTime64(3, 'UTC'),
    _inserted_at     DateTime64(3, 'UTC') DEFAULT now64()
)
ENGINE = ReplacingMergeTree(_inserted_at)
PARTITION BY toYYYYMM(valid_time)
ORDER BY (symbol, valid_time)
TTL valid_time + INTERVAL 180 DAY;

-- ─────────────────────────────────────────────
-- 4. Indicator Results (RSI, MACD, BB, VWAP, ATR, Pivot)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS indicator_results
(
    symbol               String,
    -- RSI
    rsi_value            Float64,
    rsi_signal           String,
    -- MACD
    macd_value           Float64,
    macd_signal          Float64,
    macd_histogram       Float64,
    macd_crossover       String,
    -- Bollinger Bands
    bb_upper             Float64,
    bb_middle            Float64,
    bb_lower             Float64,
    bb_width             Float64,
    bb_signal            String,
    -- VWAP
    vwap_value           Float64,
    vwap_deviation       Float64,
    vwap_signal          String,
    -- ATR
    atr_value            Float64,
    atr_percent          Float64,
    -- Pivot Points
    pivot                Float64,
    pivot_r1             Float64,
    pivot_r2             Float64,
    pivot_s1             Float64,
    pivot_s2             Float64,
    -- Aggregiertes Signal
    signal               String,          -- BUY / SELL / HOLD
    valid_time           DateTime64(3, 'UTC'),
    transaction_time     DateTime64(3, 'UTC'),
    _inserted_at         DateTime64(3, 'UTC') DEFAULT now64()
)
ENGINE = ReplacingMergeTree(_inserted_at)
PARTITION BY toYYYYMM(valid_time)
ORDER BY (symbol, valid_time)
TTL valid_time + INTERVAL 365 DAY;

-- ─────────────────────────────────────────────
-- 5. Trade Signals (Output des Signal Aggregators)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS trade_signals
(
    symbol             String,
    action             String,            -- BUY / SELL
    price              Float64,
    atr                Float64,
    indicator_signal   String,
    sentiment_signal   String,
    sentiment_score    Float64,
    valid_time         DateTime64(3, 'UTC'),
    transaction_time   DateTime64(3, 'UTC'),
    _inserted_at       DateTime64(3, 'UTC') DEFAULT now64()
)
ENGINE = ReplacingMergeTree(_inserted_at)
PARTITION BY toYYYYMM(valid_time)
ORDER BY (symbol, valid_time);

-- ─────────────────────────────────────────────
-- 6. Risk Decisions (Output des Risk Managers)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS risk_decisions
(
    symbol           String,
    action           String,
    price            Float64,
    quantity         Int32,
    stop_loss        Float64,
    take_profit      Float64,
    position_value   Float64,
    risk_amount      Float64,
    approved         Bool,
    reason           String,
    valid_time       DateTime64(3, 'UTC'),
    transaction_time DateTime64(3, 'UTC'),
    _inserted_at     DateTime64(3, 'UTC') DEFAULT now64()
)
ENGINE = ReplacingMergeTree(_inserted_at)
PARTITION BY toYYYYMM(valid_time)
ORDER BY (symbol, valid_time);

-- ─────────────────────────────────────────────
-- 7. Order Results (Output des Order Executors)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS order_results
(
    order_id         String,
    symbol           String,
    action           String,
    quantity         Int32,
    order_type       String,             -- market / limit
    status           String,             -- submitted / failed
    stop_loss        Float64,
    take_profit      Float64,
    error            Nullable(String),
    valid_time       DateTime64(3, 'UTC'),
    transaction_time DateTime64(3, 'UTC'),
    _inserted_at     DateTime64(3, 'UTC') DEFAULT now64()
)
ENGINE = ReplacingMergeTree(_inserted_at)
PARTITION BY toYYYYMM(transaction_time)
ORDER BY (symbol, transaction_time);

-- ─────────────────────────────────────────────
-- Nuetzliche Analyseabfragen (als Kommentar)
-- ─────────────────────────────────────────────

-- Trefferquote der letzten 30 Tage:
-- SELECT
--     countIf(status = 'submitted') AS total_trades,
--     countIf(action = 'BUY') AS buys,
--     countIf(action = 'SELL') AS sells
-- FROM order_results
-- WHERE transaction_time >= now() - INTERVAL 30 DAY;

-- Durchschnittlicher Sentiment-Score pro Symbol:
-- SELECT symbol, avg(sentiment_score) AS avg_sentiment
-- FROM sentiment_results
-- WHERE valid_time >= now() - INTERVAL 7 DAY
-- GROUP BY symbol
-- ORDER BY avg_sentiment DESC;

-- RSI-Verteilung wenn BUY-Signal ausgeloest wurde:
-- SELECT avg(i.rsi_value), min(i.rsi_value), max(i.rsi_value)
-- FROM indicator_results i
-- WHERE i.signal = 'BUY'
-- AND i.valid_time >= now() - INTERVAL 30 DAY;
