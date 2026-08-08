from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_MODEL_BUNDLE_PATH = "artifacts/models/production_model_bundle.joblib"


class Settings(BaseSettings):
    postgres_user: str = "credit_user"
    postgres_password: str = "credit_pass"
    postgres_db: str = "credit_risk"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_name: str = "Credit Risk Scoring Service"
    app_env: str = "dev"

    database_url: str | None = None
    model_bundle_path: str | None = None
    inference_logging_enabled: bool = True
    database_required: bool = True
    top_reason_codes: int = 5
    max_batch_size: int = 1000
    batch_storage_dir: str = "artifacts/uploads"
    batch_output_dir: str = "artifacts/predictions"
    batch_max_upload_bytes: int = 50_000_000
    batch_max_rows: int = 100_000
    batch_worker_poll_seconds: float = 2.0
    batch_retain_inputs: bool = False
    api_key: SecretStr | None = None
    partner_postback_secret: SecretStr | None = None
    partner_config_path: str = "configs/partners.yaml"
    experiment_config_path: str = "configs/experiments.yaml"
    demo_mode: bool = True
    real_partner_enabled: bool = False
    real_partner_secret: SecretStr | None = None
    operator_api_key_required: bool = True
    public_auth_strict: bool = False
    offer_config_path: str = "configs/offers.yaml"
    offer_reference_annual_rate: float = 0.24
    offer_ranker_mode: Literal["rules", "ml"] = "rules"
    offer_ranker_min_samples: int = 200
    offer_ranking_dataset_path: str = "data/processed/offer_ranking_train.parquet"
    offer_ranking_dataset_report_path: str = (
        "artifacts/reports/offer_ranking_dataset_report.json"
    )
    offer_ranker_model_path: str = "artifacts/models/offer_ranker.joblib"
    offer_ranker_metrics_path: str = "artifacts/metrics/offer_ranker_metrics.json"
    offer_ranker_report_path: str = "artifacts/reports/offer_ranker_report.json"
    persist_exact_commercial_values: bool = False
    analytics_default_days: Literal[7, 30, 90] = 30
    rate_limit_enabled: bool = True
    rate_limit_window_seconds: int = 60
    rate_limit_profile_score: int = 60
    rate_limit_offer_match: int = 30
    rate_limit_offer_click: int = 60
    rate_limit_partner_postback: int = 30
    rate_limit_invalid_postback: int = 8
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_commercial_safety(self) -> "Settings":
        if self.real_partner_enabled and (
            self.real_partner_secret is None
            or not self.real_partner_secret.get_secret_value().strip()
        ):
            raise ValueError("REAL_PARTNER_SECRET is required when REAL_PARTNER_ENABLED=true")
        if (
            self.public_auth_strict
            and self.app_env.lower() in {"production", "prod", "public"}
            and (self.api_key is None or not self.api_key.get_secret_value().strip())
        ):
            raise ValueError("API_KEY is required for a strict public deployment")
        return self

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    def resolve_model_bundle_path(self, configured_path: str | None = None) -> str:
        """Apply one deployment override consistently across all inference jobs."""
        return self.model_bundle_path or configured_path or DEFAULT_MODEL_BUNDLE_PATH


settings = Settings()
