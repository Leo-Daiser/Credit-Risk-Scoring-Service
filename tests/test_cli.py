"""Tests for the ``src.cli`` command-line entrypoint.

These tests must NOT require real Kaggle data, a real database or real model
training. Every command handler is exercised by monkeypatching the underlying
functions that ``src.cli`` imports, so we only verify that the CLI dispatches
to the correct function with the expected arguments.
"""

import pytest

import src.cli as cli


def test_cli_unknown_command_raises():
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["totally-unknown-command"])

    message = str(excinfo.value)
    assert "Unknown command: totally-unknown-command" in message
    assert "Available commands:" in message


def test_cli_no_command_raises():
    with pytest.raises(SystemExit) as excinfo:
        cli.main([])

    assert "Available commands:" in str(excinfo.value)


def test_cli_init_db_command_calls_init_db(monkeypatch, capsys):
    calls = {"count": 0}

    def fake_init_db():
        calls["count"] += 1

    monkeypatch.setattr(cli, "init_db", fake_init_db)

    cli.main(["init-db"])

    assert calls["count"] == 1
    assert "Database initialized." in capsys.readouterr().out


def test_cli_validate_raw_command_calls_expected_functions(monkeypatch, capsys):
    calls = {}

    def fake_load_data_config(path):
        calls["config_path"] = path
        return {"sentinel": "config"}

    def fake_load_raw_tables(path):
        calls["tables_path"] = path

        class _DummyDF:
            shape = (10, 3)

        return {"application_train": _DummyDF()}

    def fake_validate_raw_tables(tables, config, strict_fk):
        calls["tables"] = tables
        calls["config"] = config
        calls["strict_fk"] = strict_fk
        return {
            "fk_report": {
                "relationship_name": "bureau->application_train",
                "orphan_count": 0,
                "orphan_ratio": 0.0,
                "sample_orphans": [],
            }
        }

    monkeypatch.setattr(cli, "load_data_config", fake_load_data_config)
    monkeypatch.setattr(cli, "load_raw_tables", fake_load_raw_tables)
    monkeypatch.setattr(cli, "validate_raw_tables", fake_validate_raw_tables)

    cli.main(["validate-raw"])

    assert calls["config_path"] == cli.DATA_CONFIG_PATH
    assert calls["tables_path"] == cli.DATA_CONFIG_PATH
    assert calls["strict_fk"] is False
    assert calls["config"] == {"sentinel": "config"}
    assert "Raw data validation completed." in capsys.readouterr().out


def test_cli_build_application_features_command_calls_runner(monkeypatch, capsys):
    calls = {}

    def fake_runner(data_config_path, feature_config_path):
        calls["args"] = (data_config_path, feature_config_path)
        return {
            "train_shape": (100, 20),
            "test_shape": (50, 20),
            "train_path": "data/processed/application_train_features.parquet",
            "test_path": "data/processed/application_test_features.parquet",
        }

    monkeypatch.setattr(cli, "run_build_application_features", fake_runner)

    cli.main(["build-application-features"])

    assert calls["args"] == (cli.DATA_CONFIG_PATH, cli.FEATURE_CONFIG_PATH)
    out = capsys.readouterr().out
    assert "Application-level features built." in out
    assert "(100, 20)" in out


def test_cli_build_bureau_features_command_calls_runner(monkeypatch, capsys):
    calls = {}

    def fake_runner(data_config_path, feature_config_path):
        calls["args"] = (data_config_path, feature_config_path)
        return {
            "shape": (300, 15),
            "unique_applicants": 300,
            "feature_count": 14,
            "output_path": "data/processed/bureau_features.parquet",
        }

    monkeypatch.setattr(cli, "run_build_bureau_features", fake_runner)

    cli.main(["build-bureau-features"])

    assert calls["args"] == (cli.DATA_CONFIG_PATH, cli.FEATURE_CONFIG_PATH)
    out = capsys.readouterr().out
    assert "Bureau features built." in out
    assert "Unique applicants: 300" in out


def test_cli_build_full_features_command_calls_runner(monkeypatch, capsys):
    calls = {}

    def fake_runner(feature_config_path):
        calls["args"] = (feature_config_path,)
        return {
            "train_shape": (100, 30),
            "test_shape": (50, 30),
            "feature_count": 28,
            "train_output_path": "data/processed/train_features.parquet",
            "test_output_path": "data/processed/test_features.parquet",
        }

    monkeypatch.setattr(cli, "run_build_full_feature_dataset", fake_runner)

    cli.main(["build-full-features"])

    assert calls["args"] == (cli.FEATURE_CONFIG_PATH,)
    out = capsys.readouterr().out
    assert "Full train/test feature datasets built." in out
    assert "Feature count: 28" in out


def test_cli_train_baseline_command_calls_runner(monkeypatch, capsys):
    calls = {}

    def fake_runner(config_path):
        calls["args"] = (config_path,)
        return {
            "model_type": "logistic_regression_baseline",
            "train_rows": 80,
            "valid_rows": 20,
            "feature_count": 28,
            "numeric_feature_count": 20,
            "categorical_feature_count": 8,
            "encoded_feature_count": 35,
            "roc_auc": 0.751234,
            "pr_auc": 0.234567,
            "best_threshold": 0.4,
            "best_threshold_metric": "f1",
            "best_threshold_metric_value": 0.512345,
            "convergence_warning": True,
            "model_output_path": "artifacts/models/logistic_regression_baseline.joblib",
            "metrics_output_path": "artifacts/metrics/baseline_metrics.json",
            "feature_schema_output_path": "artifacts/reports/feature_schema.json",
            "evaluation_report_output_path": (
                "artifacts/reports/evaluation_report.json"
            ),
        }

    monkeypatch.setattr(cli, "train_logistic_regression_baseline", fake_runner)

    cli.main(["train-baseline"])

    assert calls["args"] == (cli.TRAIN_CONFIG_PATH,)
    out = capsys.readouterr().out
    assert "Logistic Regression baseline trained." in out
    assert "Model type: logistic_regression_baseline" in out
    assert "ROC-AUC: 0.751234" in out
    assert "Encoded feature count: 35" in out
    assert "Best threshold: 0.4" in out
    assert "Convergence warning: True" in out
    assert "Evaluation report saved to:" in out
