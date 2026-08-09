import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

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


def test_alembic_chain_contains_offer_import_and_saas_disclosure_revisions():
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    head = scripts.get_current_head()
    assert head == "20260809_08"
    assert scripts.get_revision(head).down_revision == "20260808_07"
    assert scripts.get_revision("20260808_07").down_revision == "20260808_06"
