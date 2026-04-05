from src.core.config import settings

def test_settings_loaded():
    assert settings.app_name == "Credit Risk Scoring Service"