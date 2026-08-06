import pytest

from src.db.migrate import classify_schema


def test_classify_schema_states():
    assert classify_schema([]) == "empty"
    assert classify_schema(["unrelated_table"]) == "empty"
    assert classify_schema(["alembic_version"]) == "managed"
    assert classify_schema(
        ["model_registry", "scoring_requests", "scoring_predictions", "feature_stats"]
    ) == "legacy"


def test_classify_schema_rejects_partial_legacy_schema():
    with pytest.raises(RuntimeError, match="partial legacy schema"):
        classify_schema(["model_registry", "scoring_requests"])
