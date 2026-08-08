# Architecture

## Общая схема

```text
data/raw/home_credit/*.csv
          |
          v
raw loader + schema/FK validation
          |
          +--> application features --------------------+
          +--> bureau + bureau_balance aggregates ------+--> full feature dataset
          `--> previous/POS/installments/card aggregates+    train/test parquet
                                                               |
                         +-------------------------------------+
                         v
              Logistic Regression baseline
              CatBoost challenger
                         |
                         v
           calibration + threshold + acceptance gates
                         |
                         v
          production_model_bundle.joblib + metadata
                 /                 |                  \
                v                  v                   v
        FastAPI /score        batch scoring       drift monitoring
                |                  |                   |
                v                  v                   v
       PostgreSQL audit      predictions file       PSI report
```

## Raw data layer

`configs/data.yaml` описывает восемь Home Credit tables, filenames, required columns,
unique keys и relationships. Loader работает с относительными путями. Validation
проверяет наличие/непустоту таблиц, schema contracts, key uniqueness и foreign-key
orphans. Для известного несоответствия `bureau_balance` CLI использует report mode,
а strict mode покрыт тестами.

Raw CSV не входят в Git и нужны только для локальной пересборки pipeline.

## Feature layer

Feature builders разделены по источникам:

- `application_features.py` — очистка application columns и отношения income/credit;
- `bureau_features.py` — bureau_balance → bureau → applicant;
- `advanced_history_features.py` — previous applications, POS/CASH, installments и
  credit cards → applicant;
- `feature_dataset.py` — one-to-one merge по `SK_ID_CURR`, pruning и общий train/test
  schema contract.

Каждая history table сначала агрегируется до одной строки на applicant. Это ограничивает
память и исключает размножение строк заявки при join. Outputs задаются в
`configs/features.yaml` и сохраняются в gitignored `data/processed/`.

## Model training layer

`configs/train.yaml` содержит два независимых training sections:

- Logistic Regression baseline с sklearn preprocessing;
- CatBoost challenger с mixed numeric/categorical input.

Оба используют один deterministic stratified split. Trainers сохраняют estimator,
metrics и feature schema только после реального fit. Synthetic unit tests проверяют
pipeline без private Kaggle data.

## Production bundle

`prepare_production_model.py` замораживает source CatBoost, обучает sigmoid calibrator,
выбирает threshold на calibration rows и считает final metrics на отдельной evaluation
части. Artifact записывается только после acceptance gates.

`ModelBundle` содержит:

- calibrated estimator;
- ordered feature schema и input contract;
- decision threshold и risk bands;
- evaluation metadata и confidence intervals;
- train-only reference statistics для input diagnostics и drift;
- fingerprints source/baseline models, metrics, training parquet, config, code и
  dependencies.

Model version детерминированно выводится из fingerprint manifest. Joblib не является
безопасным форматом для недоверенных файлов, поэтому bundle должен поступать только из
контролируемого training pipeline.

## API serving

FastAPI загружает и валидирует bundle перед readiness/scoring через cached dependency.
`/score` выполняет:

1. Pydantic validation request envelope.
2. Проверку неизвестных, required и numeric features.
3. Проверку minimum non-null feature coverage.
4. Schema alignment и input-quality diagnostics.
5. Calibrated inference, threshold decision, risk band и local reason codes.
6. Atomic audit transaction.

`/health` проверяет процесс, `/ready` — bundle и PostgreSQL. Настроенный shared API
key защищает `/score`; при пустом `API_KEY` проверка отключена. Такой ключ не заменяет
полноценную user authentication/authorization.

## Batch scoring

`src/services/batch.py` читает настроенный parquet, применяет тот же `ScoringService`
и тот же bundle contract, затем записывает prediction-only parquet и summary JSON.
Лимит строк и пути находятся в `configs/service.yaml`.

Batch scoring — offline CLI job, а не HTTP endpoint или отдельный worker service.

## PostgreSQL audit log

Alembic управляет таблицами:

- `model_registry` — model identity, artifact path и metrics metadata;
- `scoring_requests` — request id, feature payload, model version и receive time;
- `scoring_predictions` — probability, risk band и reason codes;
- `feature_stats` — schema для агрегированной feature statistics.

Request и prediction сохраняются одной transaction. Duplicate `request_id` возвращает
`409`; при required logging database failure возвращается `503`, а не ложный success.

## Drift monitoring

`src/services/monitoring.py` сравнивает текущий feature parquet с reference statistics
из bundle. Report включает numeric/categorical PSI и missing-rate delta с уровнями
`ok`, `warning`, `critical`. Это offline диагностический сигнал; он не запускает
автоматическое переобучение.

## Docker Compose runtime

Compose поднимает два runtime services:

```text
PostgreSQL 16 <--- FastAPI container
                     |
                     `--- read-only ./artifacts mount
```

API ожидает database health, применяет Alembic migration и запускается без `--reload`.
Readiness требует доступный PostgreSQL и валидный локальный bundle. Batch и monitoring
остаются отдельными CLI processes на host/container по необходимости.

Такой runtime достаточен для single-host portfolio MVP. Horizontal scaling потребует
external artifact storage, secrets management, TLS/auth gateway, rate limiting и
проверки database connection capacity.
