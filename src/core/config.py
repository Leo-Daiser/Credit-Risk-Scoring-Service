from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    model_bundle_path: str = "artifacts/models/production_model_bundle.joblib"
    inference_logging_enabled: bool = True
    database_required: bool = True
    top_reason_codes: int = 5
    max_batch_size: int = 1000
    min_feature_coverage: float = Field(default=0.01, ge=0.0, le=1.0)
    required_model_features: str = "AGE_YEARS,AMT_CREDIT,AMT_ANNUITY,AMT_INCOME_TOTAL"
    api_key: SecretStr | None = None
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def required_model_feature_list(self) -> list[str]:
        return [value.strip() for value in self.required_model_features.split(",") if value.strip()]


settings = Settings()
