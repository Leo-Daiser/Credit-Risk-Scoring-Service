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

### In progress
- историческая агрегация (bureau / bureau_balance)
- построение полного feature dataset для train/test
- model training pipeline

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
│   │   └── __init__.py
│   ├── models/
│   │   └── __init__.py
│   ├── services/
│   │   └── health.py
│   ├── utils/
│   │   └── paths.py
│   └── cli.py
├── configs/
│   ├── app.yaml
│   ├── db.yaml
│   ├── train.yaml
│   └── data.yaml
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
│   └── test_validate_schema.py
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

### Phase 3 — Historical Aggregation Layer
- bureau aggregations
- bureau_balance aggregations
- merge historical features to applicant level

### Phase 4 — Modeling Layer
- Logistic Regression baseline
- CatBoost challenger
- offline evaluation
- artifact saving

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
- feature engineering из historical tables
- train/validation split
- training pipeline
- model serving for `/score`
- explainability output
- drift monitoring
- batch inference

Это будет добавляться по фазам.

---

## Author

**Leo Daiser**  
GitHub: [Leo-Daiser](https://github.com/Leo-Daiser)

---

## License

Проект создаётся в учебно-прикладных целях.
