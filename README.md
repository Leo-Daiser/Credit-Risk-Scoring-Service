# Credit Risk Scoring Service

Production-like ML-сервис оценки вероятности дефолта на датасете Home Credit Default Risk.

Это не ноутбук с моделью, а воспроизводимый сервисный контур:

- загрузка и проверка raw data;
- feature engineering для всех восьми исходных Home Credit tables;
- Logistic Regression baseline и CatBoost challenger;
- калибровка, cost-sensitive threshold и acceptance gates без утечки в evaluation split;
- online API и batch scoring через один immutable model bundle;
- локальные SHAP reason codes;
- PostgreSQL audit log и model registry;
- input-quality diagnostics, API-key authentication и Prometheus metrics;
- bootstrap confidence intervals, subgroup report и offline drift monitoring;
- Docker Compose, Alembic migrations, CI и тесты.

## Статус проекта

Полноценный MVP сервиса реализован.

| Фаза | Результат | Статус |
|---|---|---|
| 0 | Структура, конфигурация, FastAPI, PostgreSQL, Docker | ✅ |
| 1 | Загрузка и data contracts для raw Home Credit tables | ✅ |
| 2.1 | Application-level features | ✅ |
| 2.2 | Bureau и bureau_balance aggregations | ✅ |
| 2.3 | Previous application, POS/CASH, installments и credit-card aggregations | ✅ |
| 2.4 | Финальный train/test feature dataset и feature pruning | ✅ |
| 3.1 | Logistic Regression baseline | ✅ |
| 3.2 | CatBoost challenger и сравнение на общем holdout | ✅ |
| 5 | Калибровка, business-cost threshold, CI, quality gates, subgroup report | ✅ |
| 6 | `/score`, input contract, API key, metrics, DB logging, model registry | ✅ |
| 7 | Batch scoring, PSI drift report, Alembic, CI | ✅ |

Финальный локальный production bundle:

- model: calibrated CatBoost;
- version: `catboost_calibrated-fc23c5cd419a`;
- features: `622`;
- evaluation ROC-AUC: `0.79233` (95% CI: `0.78272–0.80081`);
- evaluation PR-AUC: `0.29791` (95% CI: `0.27858–0.31985`);
- Brier score после калибровки: `0.06544`;
- expected calibration error: `0.00351`;
- operating threshold: `0.15`;
- recall / precision / F1: `0.52880 / 0.25760 / 0.34644`;
- ROC-AUC improvement over baseline on the same rows: `+0.00774`
  (paired 95% CI: `+0.00391…+0.01165`);
- acceptance gates: `passed`.

Версия строится из SHA-256 source artifact. Значения выше относятся к конкретному локальному прогону на полном датасете и не зашиты в код как гарантии.

## Архитектура

```text
raw CSV
  -> schema validation
  -> application + bureau + previous/POS/installments/card feature builders
  -> train_features.parquet / test_features.parquet
  -> baseline + CatBoost challenger
  -> calibration + cost-sensitive threshold + acceptance gates
  -> production_model_bundle.joblib
       |-> FastAPI /score
       |-> batch scoring
       |-> reference stats -> drift monitoring
       `-> model metadata / CI / subgroup report / reason codes

FastAPI /score
  -> schema alignment
  -> required-field, coverage and training-domain diagnostics
  -> calibrated probability
  -> decision + risk band + local SHAP reasons
  -> atomic PostgreSQL request/prediction log
```

Train/calibration/evaluation разделены. Source model обучается на train-части. Половина исходного holdout используется только для calibration и выбора threshold, вторая половина — только для итоговой оценки. Перед сборкой bundle split contract сверяется с metrics-манифестами source model и baseline: `random_seed`, holdout fraction и feature count обязаны совпадать. Candidate и baseline сравниваются на одних evaluation-строках, а положительное улучшение подтверждается парным bootstrap CI. Bundle сохраняется только после прохождения gates по ROC-AUC, нижней границе bootstrap CI, PR-AUC, Brier, ECE, улучшению относительно baseline и эффекту калибровки. Drift reference statistics строятся только по train-части.

## Структура репозитория

```text
credit-risk-scoring/
├── .github/workflows/ci.yml
├── migrations/
│   ├── env.py
│   └── versions/20260806_01_initial_schema.py
├── configs/
│   ├── data.yaml
│   ├── features.yaml
│   ├── service.yaml
│   └── train.yaml
├── src/
│   ├── api/
│   │   ├── dependencies.py
│   │   ├── main.py
│   │   ├── routes.py
│   │   └── schemas.py
│   ├── core/config.py
│   ├── data/
│   ├── db/
│   ├── features/
│   ├── models/
│   │   ├── model_bundle.py
│   │   ├── prepare_production_model.py
│   │   ├── train_baseline.py
│   │   └── train_catboost.py
│   ├── services/
│   │   ├── batch.py
│   │   ├── monitoring.py
│   │   └── scoring.py
│   └── cli.py
├── tests/
├── alembic.ini
├── Dockerfile
├── docker-compose.yml
├── Makefile
└── requirements.txt
```

Raw dat��9��$z{-���jם, "precision": 0.7, "recall": 0.8},
        "0.70": {"f1": 0.60, "precision": 0.9, "recall": 0.4},
    }
    result = select_best_threshold(threshold_metrics, metric_name="f1")
    assert result["metric_name"] == "f1"
    assert result["best_threshold"] == 0.50
    assert result["best_metric_value"] == 0.75
    assert result["metrics_at_best_threshold"] == threshold_metrics["0.50"]

    # The selected metric is configurable.
    precision_result = select_best_threshold(threshold_metrics, metric_name="precision")
    assert precision_result["best_threshold"] == 0.70


def test_summarize_probabilities_outputs_quantiles():
    y_proba = np.linspace(0.0, 1.0, num=101)
    summary = summarize_probabilities(y_proba)
    for key in (
        "min",
        "max",
        "mean",
        "std",
        "p01",
        "p05",
        "p25",
        "p50",
        "p75",
        "p95",
        "p99",
    ):
        assert key in summary
    assert summary["min"] == 0.0
    assert summary["max"] == 1.0
    assert summary["p50"] == pytest.approx(0.5)


def test_evaluate_binary_classifier_threshold_metrics_include_confusion_counts():
    y_true = [0, 0, 1, 1, 0, 1, 0, 1]
    y_proba = [0.1, 0.4, 0.8, 0.7, 0.2, 0.9, 0.35, 0.55]
    metrics = evaluate_binary_classifier(y_true, y_proba)
    assert metrics["threshold_metrics"]  # non-empty
    for thr, entry in metrics["threshold_metrics"].items():
        for key in ("tp", "fp", "tn", "fn"):
            assert key in entry, f"missing {key} for threshold {thr}"
        # Confusion counts must sum to the number of samples.
        assert entry["tp"] + entry["fp"] + entry["tn"] + entry["fn"] == len(y_true)


def test_train_logistic_regression_baseline_saves_evaluation_report(tmp_path):
    df = _synthetic_training_frame(n=200, seed=3)
    train_path = tmp_path / "train_features.parquet"
    df.to_parquet(train_path, index=False)

    report_path = tmp_path / "reports" / "evaluation_report.json"
    config = {
        "baseline": {
            "train_features_path": str(train_path),
            "id_column": "SK_ID_CURR",
            "target_column": "TARGET",
            "validation_size": 0.2,
            "random_seed": 42,
            "model_output_path": str(tmp_path / "models" / "logreg.joblib"),
            "metrics_output_path": str(tmp_path / "metrics" / "metrics.json"),
            "feature_schema_output_path": str(tmp_path / "reports" / "schema.json"),
            "evaluation_report_output_path": str(report_path),
            "logistic_regression": {"max_iter": 200, "solver": "saga", "C": 1.0},
            "thresholds": [0.2, 0.5, 0.8],
            "selected_threshold_metric": "f1",
        }
    }
    config_path = tmp_path / "train.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    train_logistic_regression_baseline(config_path=config_path)

    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for key in (
        "convergence_warning",
        "threshold_selection",
        "probability_summary",
        "classification_report_default_threshold",
        "classification_report_best_threshold",
    ):
        assert key in report


def test_train_logistic_regression_baseline_summary_contains_hardening_fields(
    tmp_path,
):
    df = _synthetic_training_frame(n=200, seed=4)
    train_path = tmp_path / "train_features.parquet"
    df.to_parquet(train_path, index=False)

    config = {
        "baseline": {
            "train_features_path": str(train_path),
            "id_column": "SK_ID_CURR",
            "target_column": "TARGET",
            "validation_size": 0.2,
            "random_seed": 42,
            "model_output_path": str(tmp_path / "models" / "logreg.joblib"),
            "metrics_output_path": str(tmp_path / "metrics" / "metrics.json"),
            "feature_schema_output_path": str(tmp_path / "reports" / "schema.json"),
            "evaluation_report_output_path": str(tmp_path / "reports" / "evaluation_report.json"),
        }
    }
    config_path = tmp_path / "train.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    summary = train_logistic_regression_baseline(config_path=config_path)
    for key in (
        "encoded_feature_count",
        "best_threshold",
        "best_threshold_metric",
        "convergence_warning",
        "evaluation_report_output_path",
    ):
        assert key in summary
    assert summary["encoded_feature_count"] is not None
    assert summary["encoded_feature_count"] >= 1
