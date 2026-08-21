-- DDL for Star Schema and metadata tables

-- 1. Metadata / Ops Tables
CREATE TABLE pipeline_run (
    run_id SERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    status TEXT NOT NULL, -- success, failed, partial
    rows_read INT DEFAULT 0,
    rows_loaded INT DEFAULT 0,
    rows_rejected INT DEFAULT 0,
    error_summary TEXT
);

CREATE TABLE etl_watermark (
    source TEXT PRIMARY KEY,
    last_processed_ts TIMESTAMPTZ NOT NULL,
    last_processed_file TEXT
);

CREATE TABLE etl_dead_letter (
    id SERIAL PRIMARY KEY,
    run_id INT REFERENCES pipeline_run(run_id),
    payload JSONB NOT NULL,
    error_reason TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Dimensions
CREATE TABLE dim_agent (
    agent_sk SERIAL PRIMARY KEY,
    agent_id_nk TEXT NOT NULL,
    agent_name TEXT,
    account_age_tier TEXT,
    risk_classification TEXT,
    daily_invite_limit INT,
    daily_message_limit INT,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    is_current BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX idx_dim_agent_nk ON dim_agent(agent_id_nk, is_current);

CREATE TABLE dim_lead (
    lead_sk SERIAL PRIMARY KEY,
    lead_id_nk TEXT UNIQUE NOT NULL,
    segment TEXT,
    source_channel TEXT,
    first_seen_date DATE
);

CREATE TABLE dim_campaign (
    campaign_sk SERIAL PRIMARY KEY,
    campaign_id_nk TEXT UNIQUE NOT NULL,
    campaign_name TEXT,
    objective TEXT,
    target_segment TEXT,
    start_date DATE,
    end_date DATE
);

CREATE TABLE dim_date (
    date_sk INT PRIMARY KEY, -- YYYYMMDD
    full_date DATE NOT NULL,
    year INT NOT NULL,
    month INT NOT NULL,
    day INT NOT NULL
);

-- 3. Fact Table
CREATE TABLE fact_outreach_event (
    event_sk BIGSERIAL PRIMARY KEY,
    event_id_nk TEXT UNIQUE NOT NULL,
    agent_sk INT REFERENCES dim_agent(agent_sk),
    lead_sk INT REFERENCES dim_lead(lead_sk),
    campaign_sk INT REFERENCES dim_campaign(campaign_sk),
    date_sk INT REFERENCES dim_date(date_sk),
    event_type TEXT NOT NULL, -- invite_sent, invite_accepted, message_sent, reply_received, ghosted, paused, resumed
    event_ts TIMESTAMPTZ NOT NULL,
    response_latency_hours NUMERIC,
    load_run_id INT REFERENCES pipeline_run(run_id)
);

-- 4. DQ and Analytics Tables
CREATE TABLE dq_result (
    run_id INT PRIMARY KEY REFERENCES pipeline_run(run_id),
    composite_score NUMERIC NOT NULL,
    status TEXT NOT NULL, -- PASS, WARN, FAIL
    evaluated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE dq_check_detail (
    id SERIAL PRIMARY KEY,
    run_id INT REFERENCES pipeline_run(run_id),
    check_name TEXT NOT NULL,
    dimension TEXT NOT NULL,
    pass_rate NUMERIC NOT NULL,
    details JSONB
);

CREATE TABLE fact_anomaly_score (
    id SERIAL PRIMARY KEY,
    agent_sk INT REFERENCES dim_agent(agent_sk),
    date_sk INT REFERENCES dim_date(date_sk),
    acceptance_zscore NUMERIC,
    reply_zscore NUMERIC,
    ghosting_zscore NUMERIC,
    composite_anomaly_score NUMERIC NOT NULL,
    is_flagged BOOLEAN NOT NULL,
    capacity_recommendation TEXT,
    evaluated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(agent_sk, date_sk)
);

-- Insert some dummy dates into dim_date for the last and next few years
DO $$ 
DECLARE 
    d DATE := '2023-01-01';
BEGIN 
    WHILE d <= '2028-12-31' LOOP 
        INSERT INTO dim_date (date_sk, full_date, year, month, day) 
        VALUES (
            to_char(d, 'YYYYMMDD')::INT, 
            d, 
            EXTRACT(YEAR FROM d), 
            EXTRACT(MONTH FROM d), 
            EXTRACT(DAY FROM d)
        ) ON CONFLICT DO NOTHING;
        d := d + INTERVAL '1 day';
    END LOOP;
END $$;
