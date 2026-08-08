from typing import Literal

from pydantic import SecretStr
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
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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
