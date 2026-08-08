from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.db.base import Base
from src.offers.train_offer_ranker import train_offer_ranker
from src.offers.training_dataset import build_offer_ranking_dataset


def test_empty_dataset_builder_writes_clean_report(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    report_path = tmp_path / "report.json"
    with Session(engine) as session:
        result = build_offer_ranking_dataset(
            session,
            output_path=tmp_path / "train.parquet",
            report_path=report_path,
        )
    assert result["status"] == "insufficient_data"
    assert result["rows"] == 0
    assert report_path.exists()


def synthetic_training_frame(rows=60):
    return pd.DataFrame(
        {
            "impression_id": range(rows),
            "profile_id": [f"profile-{index // 3}" for index in range(rows)],
            "offer_id": [index % 3 for index in range(rows)],
            "age_band": ["31_45"] * rows,
            "region": ["moscow"] * rows,
            "income_band": ["100k_150k", "50k_100k"] * (rows // 2),
            "employment_type": ["employee"] * rows,
            "credit_history_band": ["good"] * rows,
            "requested_amount_band": ["100k_300k"] * rows,
            "term_months": [24] * rows,
            "loan_purpose": ["cash"] * rows,
            "risk_band": ["low", "medium"] * (rows // 2),
            "pti_band": ["low", "moderate"] * (rows // 2),
            "affordability_band": ["comfortable"] * rows,
            "data_coverage": [0.8] * rows,
            "product_type": ["cash"] * rows,
            "bank_id": ["a", "b", "c"] * (rows // 3),
            "offer_priority": [50] * rows,
            "rank_shown": [1, 2, 3] * (rows // 3),
            "rule_score": [0.8, 0.7, 0.6] * (rows // 3),
            "clicked_flag": [0, 1] * (rows // 2),
            "application_started_flag": [0] * rows,
            "application_submitted_flag": [0] * rows,
            "approved_flag": [0, 1] * (rows // 2),
            "issued_flag": [0, 1] * (rows // 2),
            "commission_amount": [0, 100] * (rows // 2),
        }
    )


def test_training_requires_enough_rows_and_two_classes(tmp_path):
    dataset = tmp_path / "train.parquet"
    synthetic_training_frame(60).to_parquet(dataset, index=False)
    result = train_offer_ranker(
        dataset_path=dataset,
        model_path=tmp_path / "ranker.joblib",
        metrics_path=tmp_path / "metrics.json",
        report_path=tmp_path / "training.json",
        min_samples=20,
    )
    assert result["status"] == "trained"
    assert Path(result["model_path"]).exists()
    assert Path(result["metrics_path"]).exists()
    insufficient = train_offer_ranker(
        dataset_path=dataset,
        report_path=tmp_path / "insufficient.json",
        min_samples=100,
    )
    assert insufficient["status"] == "insufficient_data"
