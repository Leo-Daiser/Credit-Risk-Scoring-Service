# Credit Risk Scoring Service

Portfolio-grade MVP сервиса оценки вероятности дефолта на данных
Home Credit Default Risk. Репозиторий показывает полный путь от проверки raw tables
и feature engineering до versioned model bundle, FastAPI inference, PostgreSQL
audit log, batch scoring и drift report.

Поверх ML-ядра работает Riskline web/BFF и privacy-light commercial extension:
предварительный PTI, объяснимый offer matching, tracked referral events и offline
контур обучения offer ranker.

Проект не является банковской системой принятия решений. `decision` в API —
демонстрационный operating rule поверх вероятности и локального threshold, а не
юридически значимое одобрение кредита.

## Статус

Реализовано:

- data contracts для восьми Home Credit tables;
- applicant-level features из application, bureau, previous application,
  POS/CASH, installments и credit-card history;
- Logistic Regression baseline и CatBoost challenger;
- sigmoid calibration, cost-sensitive threshold и acceptance gates;
- immutable production bundle с feature schema и deterministic version;
- FastAPI `/score`, input-quality diagnostics и local reason codes;
- PostgreSQL audit logging, Alembic, batch scoring и PSI monitoring;
- Riskline web/BFF, durable batch worker и operator history;
- privacy-light profile, eligibility/ranking, click/postback learning loop;
- Docker Compose, CI, unit/integration tests и load-smoke script.

Commercial architecture и privacy-границы: [docs/commercial_matching.md](docs/commercial_matching.md).

## Результат локального обучения

Метрики ниже относятся только к конкретному локальному полному прогону на Home
Credit data и bundle `catboost_calibrated-6dba880cb73a`. Они не являются
гарантированными свойствами кода или будущих данных.

| Метрика на локальном evaluation split | Значение |
|---|---:|
| Rows | 30 752 |
| Features | 622 |
| ROC-AUC, calibrated CatBoost | 0.79233 |
| ROC-AUC 95% bootstrap CI | 0.78272–0.80081 |
| PR-AUC | 0.29791 |
| Brier score | 0.06544 |
| Expected calibration error | 0.00351 |
| Operating threshold | 0.15 |
| Recall / precision / F1 | 0.52880 / 0.25760 / 0.34644 |
| ROC-AUC improvement over baseline | +0.00774 |

Методология, baseline comparison и ограничения описаны в
[`docs/ml_report.md`](docs/ml_report.md).

## Архитектура

```text
raw CSV -> validation -> applicant-level features -> train/test parquet
        -> baseline + CatBoost -> calibration + threshold + gates
        -> trusted production bundle
             |-> FastAPI /score -> PostgreSQL audit log
             |-> batch scoring
             `-> reference statistics -> drift monitoring

privacy-light profile -> approximate PTI -> risk coverage/fallback
        -> offer eligibility -> rules/optional ML ranking
        -> impression -> click -> signed postback -> ranking dataset

browser -> Riskline server-side BFF -> FastAPI + worker -> PostgreSQL/artifacts
```

Подробное описание слоёв: [`docs/architecture.md`](docs/architecture.md).

## Требования

- Python 3.11;
- Node.js 22 для Riskline frontend;
- PostgreSQL 16 для API с audit logging;
- Docker Desktop с Compose — для production-like локального запуска;
- полный Home Credit dataset — только для пересборки features и моделей.

## Быстрый старт

В PowerShell из корня репозитория:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
Copy-Item .env.example .env
Set-Location frontend
npm ci
Set-Location ..
```

Замените `POSTGRES_PASSWORD=change-me` и задайте `API_KEY` перед использованием
за пределами изолированной локальной среды.

Базовая проверка checkout не требует Kaggle CSV или model artifacts:

```powershell
python -m pip check
ruff check src tests migrations scripts
pytest -q
docker compose config --quiet
```

## Данные и воспроизводимость

Распакуйте Kaggle tables в `data/raw/home_credit/`:

```text
application_train.csv       application_test.csv
bureau.csv                  bureau_balance.csv
previous_application.csv    POS_CASH_balance.csv
installments_payments.csv   credit_card_balance.csv
```

Полная последовательность:

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

Полученный `artifacts/models/production_model_bundle.joblib` используется online,
batch и monitoring кодом. Bundle создаётся локально и намеренно не хранится в Git.
Загружайте joblib только из доверенного training pipeline.

## CLI

Список README соответствует `src/cli.py`:

| Команда | Назначение |
|---|---|
| `init-db` | Применить Alembic migrations |
| `validate-raw` | Проверить raw tables и relationships |
| `build-application-features` | Собрать application-level features |
| `build-bureau-features` | Агрегировать bureau и bureau_balance |
| `build-advanced-history-features` | Агрегировать previous/POS/installments/card |
| `build-full-features` | Собрать финальные train/test feature tables |
| `train-baseline` | Обучить Logistic Regression baseline |
| `train-catboost` | Обучить CatBoost challenger |
| `prepare-production-model` | Калибровать, проверить gates и собрать bundle |
| `batch-score` | Выполнить offline batch scoring |
| `monitor-drift` | Построить offline PSI/missingness report |
| `seed-demo-offers` | Загрузить три синтетических demo offers |
| `build-offer-ranking-dataset` | Собрать impression-level ranking dataset |
| `train-offer-ranker` | Обучить optional ranker при прохождении data gates |
| `evaluate-offer-ranker` | Прочитать сохранённые ranker metrics |

Формат запуска: `python -m src.cli <command>`. `init-db` — совместимый alias для
того же Alembic runner:

```powershell
python -m src.cli init-db
# Эквивалентный прямой вызов:
python -m src.db.migrate
```

## API и Docker Compose

До запуска должен существовать локальный production bundle:

```powershell
docker compose up --build -d
docker compose ps
docker compose logs -f api
```

Compose поднимает PostgreSQL, FastAPI, отдельный batch worker и Riskline frontend/BFF,
применяет Alembic migrations, монтирует model bundle read-only и проверяет health.

Endpoints:

- `GET /health` — liveness процесса;
- `GET /ready` — model bundle и PostgreSQL готовы;
- `GET /model_info` — metadata текущего bundle;
- `GET /feature_schema` — machine-readable input contract;
- `POST /score` — одиночный scoring с audit logging;
- `POST /v1/profile/score` — предварительный privacy-light профиль;
- `POST /v1/offers/match` — eligibility и ранжированная выдача;
- `GET /v1/offers` — безопасные публичные поля активных offers;
- `POST /v1/offers/{offer_id}/click` — идемпотентный tracked click;
- `POST /v1/partner/postback` — подписанный и идемпотентный partner outcome;
- `GET /v1/analytics/commercial-summary` — protected product funnel aggregates;
- `GET /v1/offers/quality-report` — protected offer-quality diagnostics;
- `GET /v1/analytics/segment-opportunities` — protected underserved segments;
- `GET /v1/analytics/event-debug` — protected metadata без raw payload;
- `GET /metrics` — Prometheus exposition;
- `GET /docs` — OpenAPI UI.

Пример scoring request:

```powershell
$headers = @{ "Content-Type" = "application/json" }
if ($env:API_KEY) { $headers["X-API-Key"] = $env:API_KEY }

$body = @{
  request_id = "demo-100001"
  features = @{
    AMT_INCOME_TOTAL = 180000
    AMT_CREDIT = 450000
    AMT_ANNUITY = 24000
    AGE_YEARS = 37
    NAME_CONTRACT_TYPE = "Cash loans"
    EXT_SOURCE_2 = 0.61
    EXT_SOURCE_3 = 0.48
  }
} | ConvertTo-Json -Depth 4

Invoke-RestMethod -Method Post -Uri http://localhost:8000/score `
  -Headers $headers -Body $body
```

Required features и minimum coverage принадлежат конкретному bundle и возвращаются
через `/feature_schema`. API отклоняет неизвестные признаки, нечисловые/бесконечные
numeric values, некорректные request IDs и слишком большие payloads. При
`DATABASE_REQUIRED=true` успешный ответ не возвращается, если audit transaction не
сохранена.

## Batch и monitoring

Пути задаются в `configs/service.yaml`:

```powershell
python -m src.cli batch-score
python -m src.cli monitor-drift
```

По умолчанию оба процесса читают `data/processed/test_features.parquet`. Результаты
записываются в `artifacts/predictions/` и `artifacts/reports/`.

## Generated artifacts

В Git разрешены только `.gitkeep` внутри generated directories. Игнорируются:

- `data/raw/*`, `data/interim/*`, `data/processed/*`;
- `artifacts/models/*`, `artifacts/metrics/*`;
- `artifacts/reports/*`, `artifacts/predictions/*`;
- `artifacts/uploads/*` и generated offer-ranker artifacts;
- `.env`, virtual environment и test caches.

## Deployment

Для локального/demo/public-safe профилей используются отдельные Compose overrides.
Короткая инструкция: [demo deployment](docs/deployment_demo.md), переменные:
[environment reference](docs/env_reference.md), проверка перед публикацией:
[public checklist](docs/deployment_public_checklist.md).

## Документация

- [Матрица публичного, operator и partner-доступа](docs/endpoint_access_matrix.md)
- [ML report](docs/ml_report.md) — задача, validation, metrics и leakage controls;
- [Architecture](docs/architecture.md) — data/model/runtime layers;
- [Demo script](docs/demo_script.md) — последовательность интервью-демо;
- [Interview notes](docs/interview_notes.md) — короткие ответы по design decisions;
- [Operations](docs/operations.md) — local SLO и triage runbook;
- [Demo deployment](docs/deployment_demo.md) — Compose profiles, setup/verify и smoke;
- [Model artifact ADR](docs/adr/001-model-artifact-contract.md) — versioning и trust boundary.
- [Commercial matching](docs/commercial_matching.md) — product/ML/event architecture;
- [Safe offer import](docs/offer_import.md) — YAML/CSV validation, env-only affiliate templates и export;
- [Commercial analytics loop](docs/commercial_matching.md#analytics-и-experiment-loop) — funnel, experiments, revenue proxy и operator boundary;
- [Privacy-light contract](docs/privacy_light_data_contract.md) — collected/stored data;
- [Offer ranker model card](docs/offer_ranking_model_card.md) — targets, gates и metrics;
- [Advertising disclosure](docs/ad_disclosure.md) — referral boundary.

## Ограничения

- текущая validation случайная stratified, а не temporal/out-of-time;
- датасет Kaggle не отражает текущий production population;
- local SHAP reason codes объясняют модель, но не доказывают причинность;
- нет fairness approval, юридических credit rules и автоматического retraining;
- shared API key не заменяет user/RBAC, TLS, rate limiting и secrets manager;
- Compose рассчитан на один API instance и один PostgreSQL instance.
- demo offers не являются реальными банковскими продуктами;
- automated commercial-event retention purge пока не реализован;
- реальный ML offer ranker нельзя включать без достаточных partner outcomes.

Практический сценарий презентации: [`docs/demo_script.md`](docs/demo_script.md).

## Лицензия

MIT. Проект предназначен для учебно-прикладного использования.
