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

Raw data, processed parquet, trained models, reports and predictions не коммитятся.

## Требования

- Python 3.11;
- PostgreSQL 16 для production-like запуска;
- Docker Desktop с Compose — опционально;
- полный Home Credit Default Risk dataset для повторной сборки features и обучения.

## Установка на Windows PowerShell

В корне репозитория:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Замените `POSTGRES_PASSWORD=change-me` в `.env`.

Проверка среды:

```powershell
python --version
python -m pip check
pip-audit -r requirements.txt
ruff check src tests migrations
pytest -q
```

Ожидаемый статус текущей версии: `127 passed`.

## Данные

Используемые файлы:

```text
data/raw/home_credit/
├── application_train.csv
├── application_test.csv
├── bureau.csv
├── bureau_balance.csv
├── previous_application.csv
├── POS_CASH_balance.csv
├── installments_payments.csv
└── credit_card_balance.csv
```

Исходные таблицы проверяются на наличие файлов и обязательных колонок, пустые таблицы, уникальные ключи и foreign-key relationship.

В реальном `bureau_balance` есть ключи, отсутствующие в `bureau`. Поэтому unit-тесты используют strict FK mode, а CLI — report mode: аномалия остаётся в отчёте, но не останавливает весь pipeline.

## Полная сборка модели

В активированной `.venv`, из корня репозитория:

```powershell
python -m src.cli validate-raw
python -m src.cli build-application-features
python -m src.cli build-bureau-features
python -m src.cli build-advanced-history-features
python -m src.cli build-full-features
python -m src.cli train-baseline
python -m src.cli train-catboost
python -m src.cli prepare-production-model
```

Для production API обязателен файл:

```text
artifacts/models/production_model_bundle.joblib
```

Bundle содержит calibrated estimator, feature schema, model metadata, risk bands, confidence intervals, acceptance report, subgroup report и reference distributions. Он создаётся только из реального обучения и намеренно не хранится в Git.

## CLI

```text
python -m src.cli init-db
python -m src.cli validate-raw
python -m src.cli build-application-features
python -m src.cli build-bureau-features
python -m src.cli build-advanced-history-features
python -m src.cli build-full-features
python -m src.cli train-baseline
python -m src.cli train-catboost
python -m src.cli prepare-production-model
python -m src.cli batch-score
python -m src.cli monitor-drift
```

`init-db` — backward-compatible alias для того же migration runner. Прямой вариант:

```powershell
python -m src.db.migrate
```

## Локальный запуск API

Сначала PostgreSQL должен быть доступен по настройкам `.env`, а migration — применена:

```powershell
python -m src.db.migrate
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

Адреса:

- OpenAPI: `http://localhost:8000/docs`;
- liveness: `http://localhost:8000/health`;
- readiness: `http://localhost:8000/ready`;
- model metadata: `http://localhost:8000/model_info`.
- machine-readable input contract: `http://localhost:8000/feature_schema`;
- Prometheus metrics: `http://localhost:8000/metrics`.

`/health` показывает, что процесс жив. `/ready` возвращает `200` только если production bundle загружен и PostgreSQL отвечает.

## Docker Compose

До запуска должен существовать production model bundle. Затем:

```powershell
docker compose up --build -d
docker compose ps
docker compose logs -f api
```

Compose:

- поднимает PostgreSQL 16;
- ждёт его healthcheck;
- выполняет безопасный migration bridge и `alembic upgrade head`;
- запускает API без development `--reload`;
- монтирует `./artifacts` в read-only режиме;
- проверяет `/ready`.

Остановка без удаления данных:

```powershell
docker compose down
```

## API

### `GET /health`

```json
{
  "status": "ok",
  "service": "credit-risk-scoring"
}
```

### `GET /ready`

```json
{
  "status": "ready",
  "model_version": "catboost_calibrated-fc23c5cd419a",
  "database": "ok"
}
```

### `GET /model_info`

Возвращает version/type модели, feature count, threshold, risk bands, основные offline metrics, confidence intervals и статус acceptance gates. Сам estimator и полный feature schema наружу не выдаются.

### `GET /feature_schema`

Возвращает numeric/categorical feature names, обязательные поля и минимальное покрытие входа для текущей версии модели. Endpoint нужен клиентам для генерации и проверки scoring payload; estimator и reference distributions не раскрываются.

### `POST /score`

Request:

```json
{
  "request_id": "application-100001",
  "features": {
    "AMT_INCOME_TOTAL": 180000,
    "AMT_CREDIT": 450000,
    "AMT_ANNUITY": 24000,
    "AGE_YEARS": 37,
    "NAME_CONTRACT_TYPE": "Cash loans",
    "EXT_SOURCE_2": 0.61,
    "EXT_SOURCE_3": 0.48
  }
}
```

Все 622 признака передавать не обязательно, но обязательны `AGE_YEARS`, `AMT_CREDIT`, `AMT_ANNUITY`, `AMT_INCOME_TOTAL`, а доля непустых переданных признаков должна быть не ниже `MIN_FEATURE_COVERAGE` (по умолчанию `0.01`). Неизвестные имена, нечисловые/бесконечные numeric values, пустые request IDs и чрезмерно длинные categorical values отклоняются с `422`. Ответ содержит полноту входа и предупреждения о значениях вне обучающего диапазона или неизвестных категориях.

Если в `.env` задан `API_KEY`, запрос должен содержать заголовок `X-API-Key`. Для production пустой ключ недопустим; режим без ключа предназначен только для локальной разработки.

Response:

```json
{
  "request_id": "application-100001",
  "default_probability": 0.083,
  "decision": "approve",
  "decision_threshold": 0.15,
  "risk_band": "medium",
  "reason_codes": [
    {
      "code": "EXT_SOURCE_3",
      "feature": "EXT_SOURCE_3",
      "contribution": 0.18,
      "direction": "increases_risk",
      "description": "External credit score increased the estimated risk."
    }
  ],
  "model_version": "catboost_calibrated-fc23c5cd419a",
  "missing_feature_count": 615,
  "input_quality": {
    "supplied_feature_count": 7,
    "supplied_feature_coverage": 0.01125,
    "missing_feature_count": 615,
    "out_of_range_features": [],
    "unseen_categorical_features": [],
    "warnings": []
  },
  "latency_ms": 651.2,
  "logging_status": "persisted"
}
```

`decision` — демонстрационный operating decision, а не юридическое решение. При `DATABASE_REQUIRED=true` сервис не возвращает успешный scoring response, если audit log не записан. Повторный `request_id` возвращает `409`.

## Explainability

- CatBoost: локальные SHAP values для конкретного запроса;
- Logistic Regression fallback: локальные contributions в log-odds;
- в ответ попадают только positive contributions, повышающие риск;
- reason codes объясняют поведение модели, но не являются причинно-следственными выводами.

## PostgreSQL

Alembic migration создаёт:

- `model_registry` — version/type/path/metrics production model;
- `scoring_requests` — request id, входной feature payload, model version;
- `scoring_predictions` — probability, risk band, reason codes;
- `feature_stats` — задел для периодической агрегации feature statistics.

Запрос и prediction сохраняются одной транзакцией. При ошибке выполняется rollback.

`sql/init.sql` оставлен как legacy/reference schema; Docker Compose использует Alembic как единственный authoritative migration mechanism.

## Batch scoring

Пути и ограничения задаются в `configs/service.yaml`:

```powershell
python -m src.cli batch-score
```

По умолчанию читается `data/processed/test_features.parquet`, а результат сохраняется в:

```text
artifacts/predictions/test_batch_scores.parquet
artifacts/reports/batch_scoring_summary.json
```

Online и batch scoring используют один bundle, threshold и risk-band mapping.

## Drift monitoring

```powershell
python -m src.cli monitor-drift
```

Отчёт `artifacts/reports/drift_report.json` содержит:

- numeric/categorical PSI;
- текущий missing rate и delta к train reference;
- severity по каждому признаку;
- общий `ok`, `warning` или `critical`.

На локальном `application_test` текущий отчёт даёт `critical`: 43 critical и 16 warning features. Среди сильных сигналов — `AMT_REQ_CREDIT_BUREAU_MON` (`PSI=0.492`) и различия missingness bureau-агрегатов. Это сигнал для анализа population/data-pipeline shift, а не повод автоматически переобучать модель.

## Конфигурация

- `configs/data.yaml` — raw paths и data contracts;
- `configs/features.yaml` — feature builders и processed outputs;
- `configs/train.yaml` — baseline, CatBoost, calibration, threshold policy, quality gates и risk bands;
- `configs/service.yaml` — model bundle, batch и monitoring paths;
- `.env` — DB, runtime model path, logging policy, input contract и API key.

Основные env-параметры перечислены в `.env.example`. `DATABASE_URL` при наличии имеет приоритет над отдельными `POSTGRES_*`.

## Тесты и CI

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\pip-audit.exe -r requirements.txt
.\.venv\Scripts\ruff.exe check src tests migrations
.\.venv\Scripts\python.exe -m pytest -q
docker compose config --quiet
```

Тесты покрывают data contracts, все feature builders, pruning, baseline, CatBoost, cost-sensitive threshold, bootstrap CI, acceptance gates, calibration, subgroup report, model bundle, input quality, API key, Prometheus endpoint, local explanations, transactional persistence, batch scoring, PSI monitoring и CLI dispatch.

GitHub Actions:

- использует branch-level concurrency, чтобы не выполнять дублирующиеся или устаревшие runs;
- устанавливает зафиксированные зависимости на Python 3.11;
- проверяет production dependencies по OSV advisory database через `pip-audit`;
- поднимает PostgreSQL 16;
- применяет Alembic migration;
- запускает весь test suite;
- валидирует Compose config.
- собирает production Docker image.

## Что намеренно не входит в MVP

- fine-grained user/role authorization и rate limiting (shared API key реализован);
- TLS termination и secrets manager;
- Kubernetes и autoscaling;
- online feature store;
- streaming monitoring и автоматический retraining;
- LightGBM: после фактического превосходства CatBoost второй tree challenger не нужен для завершённости сервиса;
- юридически значимые credit-decision правила и fairness approval.

Для реального production эти пункты обязательны в зависимости от регуляторного и инфраструктурного контекста. Текущий проект является полноценным portfolio-grade service MVP, но не банковской системой принятия решений.

## Лицензия

MIT. Проект предназначен для учебно-прикладного использования.
