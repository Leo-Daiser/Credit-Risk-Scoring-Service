from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

from src.core.config import settings

DEFAULT_VARIANT = "rules_v1"
ALLOWED_VARIANTS = {
    DEFAULT_VARIANT,
    "rules_revenue_weighted_v1",
    "rules_fit_heavy_v1",
}


def load_experiment_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path or settings.experiment_config_path)
    if not config_path.exists():
        return {"enabled": False, "traffic_split": {DEFAULT_VARIANT: 1.0}}
    with config_path.open("r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    return config if isinstance(config, dict) else {}


def _validated_split(config: dict[str, Any]) -> list[tuple[str, float]] | None:
    if not config.get("enabled", False):
        return None
    split = config.get("traffic_split")
    if not isinstance(split, dict) or not split:
        return None
    normalized: list[tuple[str, float]] = []
    total = 0.0
    for variant, raw_weight in split.items():
        if variant not in ALLOWED_VARIANTS:
            return None
        try:
            weight = float(raw_weight)
        except (TypeError, ValueError):
            return None
        if weight < 0:
            return None
        normalized.append((variant, weight))
        total += weight
    if abs(total - 1.0) > 1e-6 or total <= 0:
        return None
    return normalized


def assign_experiment_variant(
    anonymous_session_id: str | None,
    config: dict[str, Any] | None = None,
) -> str:
    resolved = config if config is not None else load_experiment_config()
    split = _validated_split(resolved)
    if split is None or not anonymous_session_id:
        return DEFAULT_VARIANT
    salt = str(resolved.get("salt", "offer-ranking"))
    digest = hashlib.sha256(f"{salt}:{anonymous_session_id}".encode()).digest()
    bucket = int.from_bytes(digest[:8], "big") / float(2**64)
    cumulative = 0.0
    for variant, weight in split:
        cumulative += weight
        if bucket < cumulative:
            return variant
    return DEFAULT_VARIANT


def strategy_multipliers(
    variant: str,
    config: dict[str, Any] | None = None,
) -> tuple[float, float]:
    resolved = config if config is not None else load_experiment_config()
    strategies = resolved.get("strategies", {})
    strategy = strategies.get(variant, {}) if isinstance(strategies, dict) else {}
    try:
        fit = float(strategy.get("fit_multiplier", 1.0))
        revenue = float(strategy.get("revenue_multiplier", 1.0))
    except (TypeError, ValueError):
        return 1.0, 1.0
    if fit <= 0 or revenue < 0:
        return 1.0, 1.0
    return min(fit, 2.0), min(revenue, 2.0)
