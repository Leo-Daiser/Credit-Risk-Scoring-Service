from typing import Any, Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_MODEL_BUNDLE_PATH = "artifacts/models/production_model_bundle.joblib"
PLACEHOLDER_SECRETS = {
    "change-me",
    "change-me-local-operator-key",
    "changeme",
    "demo",
    "example",
    "placeholder",
    "secret",
}


class Settings(BaseSettings):
    postgres_user: str = "credit_user"
    postgres_password: str = "credit_pass"
    postgres_db: str = "credit_risk"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_name: str = "Credit Risk Scoring Service"
    app_env: Literal["local", "demo", "public"] = "local"

    database_url: str | None = None
    model_bundle_path: str | None = None
    model_bundle_required: bool = False
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
    partner_postbacks_enabled: bool = True
    partner_config_path: str = "configs/partners.yaml"
    experiment_config_path: str = "configs/experiments.yaml"
    demo_mode: bool = True
    public_safe_demo_adapter_enabled: bool = False
    real_partner_enabled: bool = False
    real_partner_secret: SecretStr | None = None
    operator_ui_enabled: bool = True
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
    rate_limit_public_event: int = 120
    rate_limit_partner_postback: int = 30
    rate_limit_invalid_postback: int = 8
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_environment_names(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        normalized = dict(values)
        app_env = str(normalized.get("app_env", "local")).strip().lower()
        normalized["app_env"] = {
            "dev": "local",
            "development": "local",
            "prod": "public",
            "production": "public",
        }.get(app_env, app_env)
        analytics_days = normalized.get("analytics_default_days")
        if isinstance(analytics_days, str) and analytics_days.isdecimal():
            normalized["analytics_default_days"] = int(analytics_days)
        return normalized

    @model_validator(mode="after")
    def validate_commercial_safety(self) -> "Settings":
        if self.real_partner_enabled and (
            self.real_partner_secret is None
            or not self.real_partner_secret.get_secret_value().strip()
        ):
            raise ValueError("REAL_PARTNER_SECRET is required when REAL_PARTNER_ENABLED=true")
        if self.app_env == "public":
            if self.demo_mode:
                raise ValueError("DEMO_MODE must be false when APP_ENV=public")
            if self.operator_ui_enabled:
                raise ValueError("OPERATOR_UI_ENABLED must be false when APP_ENV=public")
            if not self.public_auth_strict:
                raise ValueError("PUBLIC_AUTH_STRICT must be true when APP_ENV=public")
            if self.api_key is None or not self.api_key.get_secret_value().strip():
                raise ValueError("API_KEY is required for a strict public deployment")
            for name, secret in (
                ("API_KEY", self.api_key),
                ("PARTNER_POSTBACK_SECRET", self.partner_postback_secret),
                ("REAL_PARTNER_SECRET", self.real_partner_secret),
            ):
                if secret is not None and secret.get_secret_value().strip().lower() in PLACEHOLDER_SECRETS:
                    raise ValueError(f"{name} cannot use a placeholder in public mode")
            if not self.database_url:
                raise ValueError("DATABASE_URL is required when APP_ENV=public")
            if self.partner_postbacks_enabled and (
                self.partner_postback_secret is None
                or not self.partner_postback_secret.get_secret_value().strip()
            ):
                raise ValueError(
                    "PARTNER_POSTBACK_SECRET is required when partner callbacks are enabled"
                )
            if self.public_safe_demo_adapter_enabled and self.partner_postbacks_enabled:
                raise ValueError(
                    "Public safe demo adapter cannot be combined with partner callbacks"
                )
        return self

    @property
    def demo_adapter_allowed(self) -> bool:
        return self.demo_mode or (
            self.is_public and self.public_safe_demo_adapter_enabled
        )

    @property
    def is_public(self) -> bool:
        return self.app_env == "public"

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
