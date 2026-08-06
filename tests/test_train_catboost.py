import json

import numpy as np
import pandas as pd
import yaml

from src.models.train_catboost import (
    CatBoostFramePreprocessor,
    train_catboost_challenger,
)


def test_catboost_frame_preprocessor_preserves_named_dataframe():
    source = pd.DataFrame(
        {
            "NUM": ["1.5", "bad"],
            "CAT": ["A", None],
            "UNUSED": [1, 2],
        }
    )
    transformer = CatBoostFramePreprocessor(["NUM"], ["CAT"])
    transformed = transformer.fit_transform(source)
    assert list(transformed.columns) == ["NUM", "CAT"]
    assert transformed.loc[0, "NUM"] == 1.5
    assert np.isnan(transformed.loc[1, "NUM"])
    assert transformed.loc[1, "CAT"] == "__MISSING__"


def test_train_catboost_challenger_end_to_end(tmp_path):
    rng = np.random.default_rng(11)
    n = 180
    age = rng.integers(20, 70, n)
    income = rng.normal(120_000, 30_000, n)
    contract = rng.choice(["cash", "revolving"], n)
    target = ((income < 110_000) | ((age < 30) & (contract == "cash"))).astype(int)
    data = pd.DataFrame(
        {
            "SK_ID_CURR": np.arange(n),
            "TARGET": target,
            "AGE": age,
            "INCOME": income,
            "CONTRACT": contract,
        }
    )
    train_path = tmp_path / "train.parquet"
    model_path = tmp_path / "catboost.joblib"
    metrics_path = tmp_path / "metrics.json"
    schema_path = tmp_path / "schema.json"
    data.to_parquet(train_path, index=False)
    config = {
        "baseline": {
            "train_features_path": "unused",
            "id_column": "SK_ID_CURR",
            "target_column": "TARGET",
            "validation_size": 0.2,
            "random_seed": 42,
            "model_output_path": "unused",
            "metrics_output_path": "unused",
            "feature_schema_output_path": "unused",
        },
        "catboost_challenger": {
            "train_features_path": str(train_path),
            "id_column": "SK_ID_CURR",
            "target_column": "TARGET",
            "validation_size": 0.2,
            "random_seed": 42,
            "model_output_path": str(model_path),
            "metrics_output_path": str(metrics_path),
            "feature_schema_output_path": str(schema_path),
            "thresholds": [0.2, 0.5, 0.8],
            "catboost": {"iterations": 20, "depth": 4, "thread_count": 1},
        },
    }
    config_path = tmp_path / "train.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    summary = train_catboost_challenger(config_path)

    assert model_path.exists()
    assert metrics_path.exists()
    assert schema_path.exists()
    assert summary["model_type"] == "catboost_challenger"
    assert 0.0 <= summary["roc_auc"] <= 1.0
    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert payload["top_feature_importances"]
    assert payload["train_rows"] + payload["valid_rows"] == n
