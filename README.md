# Credit Risk Scoring Service

Production-like ML system for credit default risk scoring based on the **Home Credit Default Risk** dataset.

Проект строится не как один ноутбук с моделью, а как инженерная ML-система с:
- модульным `src/`
- конфигами
- PostgreSQL
- FastAPI
- Docker Compose
- CLI-командами
- тестами
- воспроизводимой загрузкой и валидацией сырых данных

---

## Current status

Сейчас реализованы:

### Phase 0 — Foundation Layer
- базовая структура репозитория
- FastAPI сервис
- health endpoint
- PostgreSQL
- SQLAlchemy ORM models
- Docker / Docker Compose
- CLI для инициализации БД
- базовые тесты

### Phase 1 — Raw Data Layer
- конфиг данных через `configs/data.yaml`
- загрузка сырых CSV
- валидация схемы таблиц
- проверка обязательных колонок
- проверка пустых таблиц
- проверка уникальных ключей
- проверка foreign key relationships
- data quality diagnostics для реального датасета
- unit-тесты на raw data contracts

### Phase 2.1 — Application-level Feature Engineering Layer
- конфиг признаков через `configs/features.yaml`
- модуль `src/features/application_features.py`
- очистка application-таблиц (аномалия `DAYS_EMPLOYED == 365243`, замена `inf`/`-inf` на `NaN`)
- производные признаки уровня заявки (ratio-фичи через safe division, `AGE_YEARS`, `EMPLOYMENT_YEARS`, агрегаты `EXT_SOURCE_*`)
- выравнивание колонок train/test (одинаковый набор фич, `TARGET` только в train)
- сохранение feature dataset в parquet (`data/processed/`)
- CLI-команда `build-application-features`
- unit-тесты на feature engineering

### Phase 2.2 — Bureau / Bureau Balance Historical Aggregation Layer
- модуль `src/features/bureau_features.py`
- агрегация `bureau_balance` до уровня кредита (`SK_ID_BUREAU`): длина истории
  (`BUREAU_BALANCE_MONTHS_COUNT/MIN/MAX`), статус-счётчики и ratio
  (`BUREAU_BALANCE_STATUS_<0..5,C,X>_COUNT/RATIO`), DPD-сигналы
  (`BUREAU_BALANCE_DPD_COUNT/RATIO`) и bad-debt
  (`BUREAU_BALANCE_BAD_DEBT_COUNT/RATIO`)
- left-join балансовых фич в `bureau` с сохранением всех строк (кредиты без
  истории получают `0` в count-колонках)
- агрегация `bureau` до уровня заявителя (`SK_ID_CURR`): числовые агрегаты,
  счётчики `CREDIT_ACTIVE`, разнообразие `CREDIT_TYPE`, безопасные ratio-фичи
- результат мерджится в application-level фичи по `SK_ID_CURR`
- сохранение в parquet (`data/processed/bureau_features.parquet`)
- CLI-команда `build-bureau-features`
- unit-тесты на bureau feature engineering

### Phase 2.3 — Full Feature Dataset Builder
- модуль `src/features/feature_dataset.py`
- сборка финальных train/test ML-датасетов из готовых feature parquet-файлов
  (`application_train_features` + `application_test_features` + `bureau_features`)
- left join application-фич с bureau-фичами по `SK_ID_CURR` (без row explosion,
  заявители без кредитной истории получают `NaN`)
- детерминированный порядок колонок (`SK_ID_CURR` первой, `TARGET` второй в
  train, остальные по алфавиту), замена `inf`/`-inf` на `NaN`
- сохранение в parquet (`data/processed/train_features.parquet`,
  `data/processed/test_features.parquet`)
- CLI-команда `build-full-features`
- unit-тесты на сборку feature dataset

### Phase 3.1 — Logistic Regression Baseline
- модуль `src/models/train_baseline.py`
- первый реальный ML-baseline: `LogisticRegression` внутри sklearn `Pipeline`
- препроцессинг через `ColumnTransformer`: numeric —
  `SimpleImputer(median)` + `StandardScaler`; categorical —
  `SimpleImputer(most_frequent)` + `OneHotEncoder(handle_unknown="ignore")`
- стратифицированный train/validation split (детерминированный seed)
- метрики классификации (`roc_auc`, `pr_auc`, `f1`, `precision`, `recall`,
  `brier_score`, `confusion_matrix`, `positive_rate`,
  `predicted_positive_rate`, `threshold_metrics`)
- сохранение артефактов: модель (`.joblib`), метрики (`.json`),
  feature schema (`.json`)
- CLI-команда `train-baseline`
- unit-тесты на train pipeline (включая end-to-end на синтетике)

### Phase 3.1.1 — Baseline hardening + evaluation report
- настраиваемые гиперпараметры `LogisticRegression` через
  `baseline.logistic_regression.*` (`max_iter`, `solver`, `class_weight`,
  `n_jobs`, `C`)
- захват `ConvergenceWarning`: обучение не падает, флаг и сообщения
  пишутся в отчёт (`convergence_warning`, `convergence_warning_messages`)
- настраиваемая сетка порогов + полные confusion-счётчики (`tp/fp/tn/fn`)
  для каждого порога
- автоматический выбор лучшего порога (`select_best_threshold`) по
  настраиваемой метрике (`selected_threshold_metric`, по умолчанию `f1`)
- сводка по вероятностям (`summarize_probabilities`: min/max/mean/std и
  перцентили p01…p99)
- `classification_report` (sklearn, `output_dict=True`) для порога `0.5` и
  для выбранного лучшего порога
- отдельный artifact с подробным отчётом:
  `artifacts/reports/logistic_regression_baseline_evaluation_report.json`

#### Baseline evaluation
- Logistic Regression — первая референсная (baseline) модель.
- Использует sklearn `Pipeline` с numeric- и categorical-препроцессингом.
- Первый локальный прогон дал примерно:
  - ROC-AUC ≈ 0.757
  - PR-AUC ≈ 0.243
- Эти значения зависят от конкретного локального запуска и **не** должны
  жёстко задаваться как гарантированные.
- Если возникает `ConvergenceWarning`, пайплайн фиксирует его в evaluation
  report (не прерывая обучение).
- Артефакты оценки сохраняются в:
  - `artifacts/metrics/logistic_regression_baseline_metrics.json`
  - `artifacts/reports/logistic_regression_baseline_evaluation_report.json`
  - `artifacts/reports/logistic_regression_baseline_feature_schema.json`
- Все эти артефакты в `.gitignore` и не коммитятся в репозиторий.

---

## Project goal

Построить сервис скоринга кредитного риска, который на вход принимает данные клиента, а на выходе возвращает:
- вероятность дефолта
- risk band
- reason codes / explainability fields
- версию модели
- логирование результатов в БД

---

## Dataset

Используется датасет **Home Credit Default Risk**.

На текущем этапе задействованы:
- `application_train.csv`
- `application_test.csv`
- `bureau.csv`
- `bureau_balance.csv`

Ожидаемая структура данных:

```text
/data/
└── raw/
    └── home_credit/
        ├── application_train.csv
        ├── application_test.csv
        ├── bureau.csv
        ├── bureau_balance.csv
```

---

## Project structure

```text
credit-risk-scoring/
├── src/
│   ├── api/
│   │   ├── main.py
│   │   ├── routes.py
│   │   └── schemas.py
│   ├── core/
│   │   ├── config.py
│   │   └── logger.py
│   ├── data/
│   │   ├── load_raw.py
│   │   └── validate_schema.py
│   ├── db/
│   │   ├── base.py
│   │   ├── models.py
│   │   ├── session.py
│   │   └── init_db.py
│   ├── features/
│   │   ├── __init__.py
│   │   ├── application_features.py
│   │   ├── bureau_features.py
│   │   └── feature_dataset.py
│   ├── models/
│   │   ├── __init__.py
│   │   └── train_baseline.py
│   ├── services/
│   │   └── health.py
│   ├── utils/
│   │   └── paths.py
│   └── cli.py
├── configs/
│   ├── app.yaml
│   ├── db.yaml
│   ├── data.yaml
│   ├── features.yaml
│   └── train.yaml
├── data/
│   ├── raw/
│   ├── interim/
│   └── processed/
├── notebooks/
├── sql/
│   └── init.sql
├── tests/
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_health.py
│   ├── test_load_raw.py
│   ├── test_validate_schema.py
│   ├── test_application_features.py
│   ├── test_bureau_features.py
│   ├── test_feature_dataset.py
│   └── test_train_baseline.py
├── artifacts/
│   ├── models/
│   ├── metrics/
│   └── reports/
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── requirements.txt
└── README.md
```

---

## Tech stack

- Python 3.11
- FastAPI
- Uvicorn
- PostgreSQL
- SQLAlchemy
- Pydantic
- pandas
- numpy
- scikit-learn
- joblib
- PyYAML
- pytest
- Docker
- Docker Compose

---

## Implemented functionality

### API
- `GET /health` — healthcheck endpoint

### Database
Сейчас в PostgreSQL заложены таблицы:
- `model_registry`
- `scoring_requests`
- `scoring_predictions`
- `feature_stats`

### CLI
Поддерживаются команды:
- `python -m src.cli init-db`
- `python -m src.cli validate-raw`
- `python -m src.cli build-application-features`
- `python -m src.cli build-bureau-features`
- `python -m src.cli build-full-features`
- `python -m src.cli train-baseline`

#### `build-application-features`
Строит application-level признаки:
- загружает только `application_train` и `application_test`;
- очищает данные и добавляет производные признаки;
- выравнивает колонки train/test (`TARGET` остаётся только в train);
- сохраняет результаты в parquet:
  - `data/processed/application_train_features.parquet`
  - `data/processed/application_test_features.parquet`
- печатает размеры train/test feature dataset.

Требует наличия реальных файлов Home Credit локально в
`data/raw/home_credit/` (raw-данные и `data/processed/` в git не коммитятся).
Конфигурация признаков задаётся в `configs/features.yaml`.

#### `build-bureau-features`
Строит applicant-level признаки кредитной истории:
- загружает только `bureau` и `bureau_balance`;
- агрегирует `bureau_balance` до уровня кредита (`SK_ID_BUREAU`);
- мерджит балансовые фичи в `bureau` (все строки сохраняются);
- агрегирует до уровня заявителя (одна строка на `SK_ID_CURR`);
- сохраняет результат в parquet:
  - `data/processed/bureau_features.parquet`
- печатает размер dataset, число заявителей и фич.

Результат мерджится в application-level фичи по `SK_ID_CURR`
(left join: заявители без кредитной истории получают `NaN`).
Требует реальных файлов Home Credit локально в `data/raw/home_credit/`.

#### `build-full-features`
Собирает финальные train/test ML-датасеты из готовых feature parquet-файлов:
- читает `application_train_features`, `application_test_features` и
  `bureau_features` из `data/processed/`;
- делает left join application-фич с bureau-фичами по `SK_ID_CURR`
  (количество строк application сохраняется, без row explosion);
- держит детерминированный порядок колонок (`SK_ID_CURR`, затем `TARGET` в
  train, остальные по алфавиту) и заменяет `inf`/`-inf` на `NaN`;
- НЕ делает импутацию / кодирование / масштабирование (это задача train
  pipeline);
- сохраняет результат в parquet:
  - `data/processed/train_features.parquet`
  - `data/processed/test_features.parquet`
- печатает размеры train/test и число фич.

Требует, чтобы upstream feature-файлы уже были собраны локально
(`build-application-features`, `build-bureau-features`). Конфигурация — секция
`full_feature_dataset` в `configs/features.yaml`.

#### `train-baseline`
Тренирует Logistic Regression baseline:
- читает `data/processed/train_features.parquet`;
- разбивает на `X`/`y` (исключая `SK_ID_CURR` и `TARGET`);
- определяет numeric / categorical фичи;
- строит sklearn `Pipeline` (препроцессинг + `LogisticRegression`);
- делает стратифицированный train/validation split;
- считает метрики на валидации;
- сохраняет артефакты:
  - `artifacts/models/logistic_regression_baseline.joblib`
  - `artifacts/metrics/logistic_regression_baseline_metrics.json`
  - `artifacts/reports/logistic_regression_baseline_feature_schema.json`
- печатает размеры выборок, число фич и ROC-AUC / PR-AUC.

Требует собранный `train_features.parquet` локально. Конфигурация — секция
`baseline` в `configs/train.yaml`. Метрики не фейкаются: JSON пишется только из
реального обучения; артефакты модели/метрик/схемы в git не коммитятся.

### Raw data validation
Проверяется:
- наличие файлов
- наличие обязательных колонок
- пустые таблицы
- уникальность ключей
- связь `bureau_balance.SK_ID_BUREAU -> bureau.SK_ID_BUREAU`

---

## Important note about raw data validation

На реальном датасете Home Credit обнаруживается data quality anomaly:

- в `bureau_balance` есть значения `SK_ID_BUREAU`, которых нет в `bureau`

Поэтому raw validation работает в двух режимах:

- **strict mode** — для unit-тестов, нарушение FK считается ошибкой
- **report mode** — для CLI на реальных данных, нарушение логируется в отчёт, но не валит весь пайплайн

Это сделано намеренно: проверка остаётся, но проект не ломается из-за особенностей исходного датасета.

---

## Installation

### 1. Clone repository

```bash
git clone https://github.com/Leo-Daiser/Credit-Risk-Scoring-Service.git
cd Credit-Risk-Scoring-Service
```

### 2. Create `.env`

Пример:

```env
POSTGRES_USER=credit_user
POSTGRES_PASSWORD=credit_pass
POSTGRES_DB=credit_risk
POSTGRES_HOST=db
POSTGRES_PORT=5432

APP_HOST=0.0.0.0
APP_PORT=8000
APP_NAME=Credit Risk Scoring Service
APP_ENV=dev
```

### 3. Install dependencies locally

```bash
pip install -r requirements.txt
```

---

## Run with Docker Compose

```bash
docker compose up --build
```

После запуска:
- API: `http://localhost:8000`
- Healthcheck: `http://localhost:8000/health`

---

## Local development

### Run API locally

```bash
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Initialize database

```bash
python -m src.cli init-db
```

### Validate raw data

```bash
python -m src.cli validate-raw
```

---

## Tests

Запуск всех тестов:

```bash
pytest -q
```

Тесты покрывают:
- config loading
- health endpoint
- raw data config loading
- table path resolution
- raw CSV loading
- required columns validation
- empty table detection
- unique key validation
- foreign key validation
- end-to-end raw schema validation on synthetic mini-tables
- safe division (zero denominator handling)
- application table cleaning (DAYS_EMPLOYED anomaly, inf/-inf)
- derived application features
- train/test feature alignment and TARGET handling
- parquet feature output
- full train/test feature dataset key contract, merge (no row explosion),
  column order, TARGET handling and parquet output (Phase 2.3)
- baseline X/y split & target validation, feature-type inference, pipeline
  construction, classification metrics, feature schema, and an end-to-end
  Logistic Regression training run on synthetic data (Phase 3.1)

Текущий статус: `pytest -q` → **77 passed**.

> Примечание: команды, зависящие от данных (`validate-raw`, `build-*-features`,
> `train-baseline`), требуют реальных файлов Home Credit / собранных датасетов
> локально. Такие команды запускаются пользователем локально. Метрики
> модели не подделываются — они появляются только из реального обучения.
>
> Что НЕ коммитится в репозиторий (см. `.gitignore`):
> - raw Kaggle CSV (`data/raw/`) — не коммитятся;
> - сгенерированные parquet (`data/processed/`, processed features) — не коммитятся;
> - артефакты обученной модели (`artifacts/models/`) — не коммитятся;
> - артефакты метрик / отчётов (`artifacts/metrics/`, `artifacts/reports/`) — не коммитятся.

---

## API

### `GET /health`

Response example:

```json
{
  "status": "ok",
  "service": "credit-risk-scoring"
}
```

---

## Configuration

Основные конфиги лежат в `configs/`.

### `configs/data.yaml`
Описывает:
- директорию с raw data
- список используемых таблиц
- обязательные колонки
- unique keys

### `configs/features.yaml`
Описывает конфигурацию feature engineering:
- `id_column` (`SK_ID_CURR`)
- `target_column` (`TARGET`)
- `days_employed_anomaly_value` (`365243`)
- `output_paths` для train/test feature parquet-файлов
- `bureau_features` — секция Phase 2.2 (`id_column`, `bureau_id_column`,
  `output_path` для bureau feature parquet-файла)
- `full_feature_dataset` — секция Phase 2.3 (пути к входным feature parquet и
  выходным `train_features` / `test_features`)

### `configs/train.yaml`
Описывает конфигурацию обучения моделей:
- `baseline` — секция Phase 3.1 (`train_features_path`, `id_column`,
  `target_column`, `validation_size`, `random_seed`, `max_iter`, пути к
  артефактам модели / метрик / feature schema)

---

## Database schema

### `model_registry`
Хранение версий моделей:
- model version
- model type
- artifact path
- metrics

### `scoring_requests`
Логирование входящих inference requests.

### `scoring_predictions`
Хранение результатов скоринга.

### `feature_stats`
Статистики признаков для мониторинга и контроля качества.

---

## Development roadmap

### Phase 2 — Base Feature Layer
- application-level cleaning ✅ (Phase 2.1)
- derived features from application tables ✅ (Phase 2.1)
- train/test feature alignment ✅ (Phase 2.1)
- save processed datasets ✅ (Phase 2.1)

### Phase 2.2 — Historical Aggregation Layer
- bureau aggregations ✅ (Phase 2.2)
- bureau_balance aggregations ✅ (Phase 2.2)
- merge historical features to applicant level ✅ (Phase 2.2)

### Phase 2.3 — Full Feature Dataset Builder
- merge application + bureau features to train/test datasets ✅ (Phase 2.3)
- deterministic column order + inf/-inf → NaN ✅ (Phase 2.3)
- save `train_features.parquet` / `test_features.parquet` ✅ (Phase 2.3)

### Phase 3 — Modeling Layer
- Logistic Regression baseline ✅ (Phase 3.1)
- offline evaluation + metrics JSON ✅ (Phase 3.1)
- model + feature schema artifact saving ✅ (Phase 3.1)
- CatBoost challenger (next)
- LightGBM (next)

### Phase 5 — Explainability and business layer
- calibration
- threshold tuning
- SHAP report
- business metrics

### Phase 6 — Serving layer
- `POST /score`
- `GET /model_info`
- inference logging
- model versioning

### Phase 7+
- batch scoring
- drift monitoring
- advanced feature pipelines
- champion / challenger logic

---

## Engineering principles

Этот проект строится с упором на:
- reproducibility
- modular code
- explicit data contracts
- separation between notebooks and production code
- testable preprocessing logic
- production-minded ML development

---

## What is intentionally not done yet

На текущем этапе **ещё не реализованы**:
- CatBoost / LightGBM challenger-модели
- калибровка вероятностей
- SHAP / reason codes / explainability output
- model serving for `/score`
- логирование inference-результатов в PostgreSQL
- batch scoring
- drift monitoring
- feature engineering из таблиц `previous_application`, `POS_CASH_balance`,
  `installments_payments`, `credit_card_balance`

Это будет добавляться по фазам.

---

## Author

**Leo Daiser**  
GitHub: [Leo-Daiser](https://github.com/Leo-Daiser)

---

## License

Проект создаётся в учебно-прикладных целях.
