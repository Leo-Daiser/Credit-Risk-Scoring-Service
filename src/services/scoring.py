"""Online scoring, explainability and persistence services."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import joblib
import numpy as np
import pandas as pd
from catboost import Pool
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.db.models import ModelRegistry, ScoringPrediction, ScoringRequest
from src.models.model_bundle import ModelBundle

logger = logging.getLogger(__name__)


class DuplicateRequestError(ValueError):
    """Raised when an idempotency request id is already persisted."""


REASON_DESCRIPTIONS = {
    "EXT_SOURCE": "External credit score increased the estimated risk.",
    "DAYS_EMPLOYED": "Employment history increased the estimated risk.",
    "AGE_YEARS": "Applicant age increased the estimated risk.",
    "CREDIT_INCOME_RATIO": "Credit amount relative to income increased the estimated risk.",
    "ANNUITY_INCOME_RATIO": "Annuity relative to income increased the estimated risk.",
    "BUREAU": "Credit bureau history increased the estimated risk.",
}


def _register_model_if_needed(session: Session, result: dict[str, Any]) -> None:
    """Register the production model without a check-then-insert race."""
    values = {
        "model_version": result["model_version"],
        "model_type": result.get("_model_type", "production_bundle"),
        "artifact_path": result.get("_artifact_path", "configured:model_bundle_path"),
        "metrics_json": result.get("_model_metrics"),
    }
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert

        statement = insert(ModelRegistry).values(**values).on_conflict_do_nothing(
            index_elements=[ModelRegistry.model_version]
        )
        session.execute(statement)
        return
    if dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert

        statement = insert(ModelRegistry).values(**values).on_conflict_do_nothing(
            index_elements=[ModelRegistry.model_version]
        )
        session.execute(statement)
        return

    if session.query(ModelRegistry).filter_by(model_version=values["model_version"]).first() is None:
        session.add(ModelRegistry(**values))


def load_model_bundle(path: str | Path) -> ModelBundle:
    bundle_path = Path(path)
    if not bundle_path.exists():
        raise FileNotFoundError(
            f"Production model bundle not found: {bundle_path}. Run "
            "`python -m src.cli prepare-production-model` first."
        )
    bundle = joblib.load(bundle_path)
    if not isinstance(bundle, ModelBundle):
        raise TypeError(f"Artifact at {bundle_path} is not a ModelBundle.")
    required_metadata = {"model_version", "model_type", "decision_threshold", "risk_bands"}
    missing = required_metadata - set(bundle.metadata)
    if missing:
        raise ValueError(f"Model bundle metadata is missing: {sorted(missing)}.")
    return bundle


def _unwrap_pipeline(model: Any) -> Any:
    """Return the fitted base estimator from a calibrated model when possible."""
    calibrated = getattr(model, "calibrated_classifiers_", None)
    if calibrated:
        candidate = calibrated[0]
        return getattr(candidate, "estimator", getattr(candidate, "base_estimator", model))
    return model


def _reason_description(feature: str) -> str:
    upper = feature.upper()
    for prefix, description in REASON_DESCRIPTIONS.items():
        if prefix in upper:
            return description
    return "This feature increased the model's estimated default risk."


def linear_reason_codes(
    model: Any,
    frame: pd.DataFrame,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return local positive log-odds contributions for sklearn linear models."""
    pipeline = _unwrap_pipeline(model)
    named_steps = getattr(pipeline, "named_steps", {})
    preprocessor = named_steps.get("preprocessor")
    classifier = named_steps.get("classifier")
    coefficients = getattr(classifier, "coef_", None)
    if preprocessor is None or coefficients is None:
        return []

    transformed = preprocessor.transform(frame)
    row = transformed.toarray()[0] if hasattr(transformed, "toarray") else np.asarray(transformed)[0]
    names = np.asarray(preprocessor.get_feature_names_out(), dtype=object)
    contributions = row * np.asarray(coefficients, dtype="float64")[0]
    positive_indices = np.flatnonzero(contributions > 0)
    ordered = positive_indices[np.argsort(contributions[positive_indices])[::-1]][:limit]

    reasons: list[dict[str, Any]] = []
    for index in ordered:
        encoded_name = str(names[index])
        feature = encoded_name.split("__", 1)[-1]
        reasons.append(
            {
                "code": feature.upper(),
                "feature": feature,
                "contribution": float(contributions[index]),
                "direction": "increases_risk",
                "description": _reason_description(feature),
            }
        )
    return reasons


def catboost_reason_codes(
    model: Any,
    frame: pd.DataFrame,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return local CatBoost SHAP contributions that increase default risk."""
    pipeline = _unwrap_pipeline(model)
    named_steps = getattr(pipeline, "named_steps", {})
    preprocessor = named_steps.get("preprocessor")
    classifier = named_steps.get("classifier")
    if preprocessor is None or classifier is None:
        return []
    if classifier.__class__.__module__.split(".")[0] != "catboost":
        return []

    transformed = preprocessor.transform(frame)
    names = list(preprocessor.get_feature_names_out())
    categorical = list(getattr(preprocessor, "categorical_features", []))
    pool = Pool(transformed, cat_features=categorical)
    shap_values = np.asarray(
        classifier.get_feature_importance(pool, type="ShapValues"),
        dtype="float64",
    )[0, :-1]
    positive_indices = np.flatnonzero(shap_values > 0)
    ordered = positive_indices[np.argsort(shap_values[positive_indices])[::-1]][:limit]
    return [
        {
            "code": str(names[index]).upper(),
            "feature": str(names[index]),
            "contribution": float(shap_values[index]),
            "direction": "increases_risk",
            "description": _reason_description(str(names[index])),
        }
        for index in ordered
    ]


def model_reason_codes(
    model: Any,
    frame: pd.DataFrame,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Dispatch local explainability to the supported estimator type."""
    reasons = linear_reason_codes(model, frame, limit=limit)
    if reasons:
        return reasons
    return catboost_reason_codes(model, frame, limit=limit)


class ScoringService:
    """Stateless inference facade around one immutable production bundle."""

    def __init__(
        self,
        bundle: ModelBundle,
        top_reason_codes: int = 5,
        artifact_path: str = "in-memory",
    ):
        self.bundle = bundle
        self.top_reason_codes = top_reason_codes
        self.artifact_path = artifact_path

    @classmethod
    def from_path(cls, path: str | Path, top_reason_codes: int = 5) -> ScoringService:
        return cls(
            load_model_bundle(path),
            top_reason_codes=top_reason_codes,
            artifact_path=str(path),
        )

    def model_info(self) -> dict[str, Any]:
        metadata = self.bundle.metadata
        calibrated = metadata.get("metrics", {}).get("calibrated", {})
        return {
            "model_version": metadata["model_version"],
            "model_type": metadata["model_type"],
            "created_at": metadata.get("created_at"),
            "feature_count": metadata.get("feature_count", len(self.bundle.feature_names)),
            "decision_threshold": metadata["decision_threshold"],
            "risk_bands": metadata["risk_bands"],
            "metrics": {
                key: calibrated.get(key)
                for key in ("roc_auc", "pr_auc", "brier_score", "expected_calibration_error")
                if key in calibrated
            },
        }

    def score(self, features: dict[str, Any], request_id: str | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        frame = self.bundle.prepare_frame([features])
        probability = float(self.bundle.predict_default_probability(frame)[0])
        threshold = float(self.bundle.metadata["decision_threshold"])
        missing_count = int(frame.iloc[0].isna().sum())
        result = {
            "request_id": request_id or str(uuid4()),
            "default_probability": probability,
            "decision": "decline" if probability >= threshold else "approve",
            "decision_threshold": threshold,
            "risk_band": self.bundle.risk_band(probability),
            "reason_codes": model_reason_codes(
                self.bundle.model, frame, limit=self.top_reason_codes
            ),
            "model_version": self.bundle.metadata["model_version"],
            "_model_type": self.bundle.metadata["model_type"],
            "_model_metrics": self.bundle.metadata.get("metrics", {}).get("calibrated"),
            "_artifact_path": self.artifact_path,
            "missing_feature_count": missing_count,
            "latency_ms": (time.perf_counter() - started) * 1000.0,
        }
        return result


def persist_scoring_result(
    session: Session,
    features: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """Persist request and prediction atomically; rollback on any failure."""
    request_id = result["request_id"]
    if session.query(ScoringRequest).filter_by(request_id=request_id).first() is not None:
        raise DuplicateRequestError(f"request_id '{request_id}' already exists.")
    try:
        version = result["model_version"]
        _register_model_if_needed(session, result)
        session.add(
            ScoringRequest(
                request_id=request_id,
                payload_json=features,
                model_version=version,
            )
        )
        # The explicit flush guarantees that the FK parent exists before the
        # prediction insert while preserving a single atomic transaction.
        session.flush()
        session.add(
            ScoringPrediction(
                request_id=request_id,
                default_probability=result["default_probability"],
                risk_band=result["risk_band"],
                top_reason_codes=result["reason_codes"],
            )
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        constraint_name = getattr(getattr(exc, "orig", None), "diag", None)
        constraint_name = getattr(constraint_name, "constraint_name", "")
        if constraint_name in {
            "scoring_requests_request_id_key",
            "uq_scoring_requests_request_id",
        }:
            raise DuplicateRequestError(
                f"request_id '{request_id}' already exists."
            ) from exc
        logger.exception("Integrity error while persisting scoring result %s", request_id)
        raise
    except Exception:
        session.rollback()
        logger.exception("Failed to persist scoring result %s", request_id)
        raise
