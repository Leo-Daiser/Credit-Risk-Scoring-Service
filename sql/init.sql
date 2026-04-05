CREATE TABLE IF NOT EXISTS model_registry (
    id SERIAL PRIMARY KEY,
    model_version VARCHAR(128) NOT NULL UNIQUE,
    model_type VARCHAR(64) NOT NULL,
    artifact_path TEXT NOT NULL,
    metrics_json JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scoring_requests (
    id SERIAL PRIMARY KEY,
    request_id VARCHAR(128) NOT NULL UNIQUE,
    payload_json JSONB NOT NULL,
    model_version VARCHAR(128),
    received_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scoring_predictions (
    id SERIAL PRIMARY KEY,
    request_id VARCHAR(128) NOT NULL,
    default_probability DOUBLE PRECISION,
    risk_band VARCHAR(32),
    top_reason_codes JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS feature_stats (
    id SERIAL PRIMARY KEY,
    feature_name VARCHAR(256) NOT NULL,
    version VARCHAR(128) NOT NULL,
    train_mean DOUBLE PRECISION,
    train_std DOUBLE PRECISION,
    missing_rate DOUBLE PRECISION,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);