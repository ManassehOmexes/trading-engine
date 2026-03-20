-- ClickHouse Schema fuer Trading Engine
-- Engine: ReplacingMergeTree fuer Deduplizierung
-- Bitemporal: valid_time + transaction_time in jeder Tabelle
-- ─────────────────────────────────────────────
-- 1. Market Ticks (Raw Trades von Alpaca)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS market_ticks (
    symbol STRING,
    price float64,
    SIZE float64,
    exchange STRING,
    valid_time datetime64(
        3,
        'UTC'
    ),
    -- Wann der Trade an der Börse stattfand
    transaction_time datetime64(
        3,
        'UTC'
    ),
    -- Wann wir ihn empfangen haben
    _inserted_at datetime64(
        3,
        'UTC'
    ) DEFAULT now64()
) engine = replacingmergetree(_inserted_at) PARTITION BY toYYYYMM(valid_time)
ORDER BY
    (
        symbol,
        valid_time
    ) ttl valid_time + INTERVAL 90 DAY;
-- ─────────────────────────────────────────────
    -- 2. Market Bars (1-Minuten OHLCV von Alpaca)
    -- ─────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS market_bars (
        symbol STRING,
        OPEN float64,
        high float64,
        low float64,
        CLOSE float64,
        volume float64,
        vwap nullable(float64),
        valid_time datetime64(
            3,
            'UTC'
        ),
        transaction_time datetime64(
            3,
            'UTC'
        ),
        _inserted_at datetime64(
            3,
            'UTC'
        ) DEFAULT now64()
    ) engine = replacingmergetree(_inserted_at) PARTITION BY toYYYYMM(valid_time)
ORDER BY
    (
        symbol,
        valid_time
    ) ttl valid_time + INTERVAL 365 DAY;
-- ─────────────────────────────────────────────
    -- 3. Sentiment Results (FinBERT Output)
    -- ─────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS sentiment_results (
        symbol STRING,
        headline STRING,
        sentiment_score float64,
        -- P(positive) - P(negative), -1 bis +1
        sentiment_signal STRING,
        -- BUY / SELL / HOLD
        POSITIVE float64,
        negative float64,
        neutral float64,
        model STRING,
        valid_time datetime64(
            3,
            'UTC'
        ),
        transaction_time datetime64(
            3,
            'UTC'
        ),
        _inserted_at datetime64(
            3,
            'UTC'
        ) DEFAULT now64()
    ) engine = replacingmergetree(_inserted_at) PARTITION BY toYYYYMM(valid_time)
ORDER BY
    (
        symbol,
        valid_time
    ) ttl valid_time + INTERVAL 180 DAY;
-- ─────────────────────────────────────────────
    -- 4. Indicator Results (RSI, MACD, BB, VWAP, ATR, Pivot)
    -- ─────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS indicator_results (
        symbol STRING,
        -- RSI
        rsi_value float64,
        rsi_signal STRING,
        -- MACD
        macd_value float64,
        macd_signal float64,
        macd_histogram float64,
        macd_crossover STRING,
        -- Bollinger Bands
        bb_upper float64,
        bb_middle float64,
        bb_lower float64,
        bb_width float64,
        bb_signal STRING,
        -- VWAP
        vwap_value float64,
        vwap_deviation float64,
        vwap_signal STRING,
        -- ATR
        atr_value float64,
        atr_percent float64,
        -- Pivot Points
        pivot float64,
        pivot_r1 float64,
        pivot_r2 float64,
        pivot_s1 float64,
        pivot_s2 float64,
        -- Aggregiertes Signal
        signal STRING,
        -- BUY / SELL / HOLD
        valid_time datetime64(
            3,
            'UTC'
        ),
        transaction_time datetime64(
            3,
            'UTC'
        ),
        _inserted_at datetime64(
            3,
            'UTC'
        ) DEFAULT now64()
    ) engine = replacingmergetree(_inserted_at) PARTITION BY toYYYYMM(valid_time)
ORDER BY
    (
        symbol,
        valid_time
    ) ttl valid_time + INTERVAL 365 DAY;
-- ─────────────────────────────────────────────
    -- 5. Trade Signals (Output des Signal Aggregators)
    -- ─────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS trade_signals (
        symbol STRING,
        action STRING,
        -- BUY / SELL
        price float64,
        atr float64,
        indicator_signal STRING,
        sentiment_signal STRING,
        sentiment_score float64,
        valid_time datetime64(
            3,
            'UTC'
        ),
        transaction_time datetime64(
            3,
            'UTC'
        ),
        _inserted_at datetime64(
            3,
            'UTC'
        ) DEFAULT now64()
    ) engine = replacingmergetree(_inserted_at) PARTITION BY toYYYYMM(valid_time)
ORDER BY
    (
        symbol,
        valid_time
    );
-- ─────────────────────────────────────────────
    -- 6. Risk Decisions (Output des Risk Managers)
    -- ─────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS risk_decisions (
        symbol STRING,
        action STRING,
        price float64,
        quantity int32,
        stop_loss float64,
        take_profit float64,
        position_value float64,
        risk_amount float64,
        approved bool,
        reason STRING,
        valid_time datetime64(
            3,
            'UTC'
        ),
        transaction_time datetime64(
            3,
            'UTC'
        ),
        _inserted_at datetime64(
            3,
            'UTC'
        ) DEFAULT now64()
    ) engine = replacingmergetree(_inserted_at) PARTITION BY toYYYYMM(valid_time)
ORDER BY
    (
        symbol,
        valid_time
    );
-- ─────────────────────────────────────────────
    -- 7. Order Results (Output des Order Executors)
    -- ─────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS order_results (
        order_id STRING,
        symbol STRING,
        action STRING,
        quantity int32,
        order_type STRING,
        -- market / limit
        status STRING,
        -- submitted / failed
        stop_loss float64,
        take_profit float64,
        error nullable(STRING),
        valid_time datetime64(
            3,
            'UTC'
        ),
        transaction_time datetime64(
            3,
            'UTC'
        ),
        _inserted_at datetime64(
            3,
            'UTC'
        ) DEFAULT now64()
    ) engine = replacingmergetree(_inserted_at) PARTITION BY toYYYYMM(transaction_time)
ORDER BY
    (
        symbol,
        transaction_time
    );
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
