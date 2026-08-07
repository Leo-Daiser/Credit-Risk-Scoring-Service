from src.core.config import DEFAULT_MODEL_BUNDLE_PATH, Settings, settings


def test_settings_loaded():
    assert settings.app_name == "Credit Risk Scoring Service"


def test_model_bundle_path_resolution_prefers_deployment_override():
    configured = "configured/model.joblib"
    without_override = Settings(_env_file=None, model_bundle_path=None)
    with_override = Settings(_env_file=None, model_bundle_path="deployed/model.joblib")

    assert without_override.resolve_model_bundle_path() == DEFAULT_MODEL_BUNDLE_PATH
    assert without_override.resolve_model_bundle_path(configured) == configured
    assert with_override.resolve_model_bundle_path(configured) == "deployed/model.joblib"
