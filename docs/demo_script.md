# Interview demo script

## 1. Введение за 60 секунд

> Это end-to-end credit-risk scoring service на Home Credit data. Я начал с raw
> contracts для восьми таблиц, агрегировал историю до applicant level и собрал общий
> feature dataset. Logistic Regression используется как baseline, CatBoost — как
> nonlinear challenger. Source model калибруется на отдельной части holdout, threshold
> выбирается по cost policy, а final metrics считаются на другой части. Результат
> упакован в versioned bundle, который одинаково используют FastAPI, batch scoring и
> drift monitoring. Online requests валидируются, получают local reason codes и
> атомарно записываются в PostgreSQL. Проект production-like, но я не называю его
> банковским production: нет temporal external validation, RBAC, TLS и regulatory
> fairness approval.

После введения покажите `README.md`, затем `docs/architecture.md` и CI.

## 2. Подготовка окружения

Из корня репозитория в PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Перед демонстрацией задайте безопасные локальные значения в `.env`. Не показывайте
реальные secrets и не добавляйте `.env` в Git.

## 3. Тесты, которые не требуют Kaggle data

```powershell
python -m pip check
ruff check src tests migrations scripts
pytest -q
docker compose config --quiet
```

Что сказать: tests создают маленькие synthetic CSV/parquet/model artifacts в temporary
directories. CI не зависит от локального Home Credit dataset или готового bundle.

## 4. Пересборка features

Эти команды требуют все восемь CSV в `data/raw/home_credit/`:

```powershell
python -m src.cli validate-raw
python -m src.cli build-application-features
python -m src.cli build-bureau-features
python -m src.cli build-advanced-history-features
python -m src.cli build-full-features
```

Проверьте результаты только локально:

```powershell
Get-ChildItem data\processed\*.parquet | Select-Object Name,Length,LastWriteTime
```

Не добавляйте parquet в Git.

## 5. Обучение моделей

```powershell
python -m src.cli train-baseline
python -m src.cli train-catboost
```

Что показать:

- baseline и challenger используют одинаковые split parameters;
- metrics пишутся только после реального fit;
- `configs/train.yaml` фиксирует seed, hyperparameters и output paths.

Artifacts в `artifacts/models`, `artifacts/metrics` и `artifacts/reports` остаются
локальными.

## 6. Production bundle

```powershell
python -m src.cli prepare-production-model
```

Проверьте metadata:

```powershell
$metadata = Get-Content artifacts\reports\production_model_metadata.json -Raw |
  ConvertFrom-Json
$metadata | Select-Object model_version,model_type,feature_count,decision_threshold
$metadata.acceptance
```

Что сказать: calibrator и threshold используют calibration half, evaluation half
используется для final metrics/gates, reference statistics строятся на train rows.
Version зависит от fingerprint manifest, а не задаётся вручную.

## 7. Запуск API

Проще всего использовать Compose:

```powershell
docker compose up --build -d
docker compose ps
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/ready
Invoke-RestMethod http://localhost:8000/model_info
```

Для host-запуска API сначала поднимите PostgreSQL и переопределите compose hostname:

```powershell
docker compose up -d db
$env:DATABASE_URL = "postgresql+psycopg2://credit_user:change-me@localhost:5432/credit_risk"
python -m src.db.migrate
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

Пароль должен совпадать с вашим `.env`. После host-демо удалите override:

```powershell
Remove-Item Env:DATABASE_URL
```

## 8. Вызов `/score`

```powershell
$headers = @{ "Content-Type" = "application/json" }
if ($env:API_KEY) { $headers["X-API-Key"] = $env:API_KEY }

$body = @{
  request_id = "interview-demo-001"
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

Покажите probability, threshold, risk band, input quality, model version,
`logging_status` и reason codes. Не называйте `decision` фактом одобрения кредита.

## 9. Проверка audit log

Для стандартных значений `.env.example`:

```powershell
docker compose exec db psql -U credit_user -d credit_risk -c `
  "SELECT request_id, model_version, received_at FROM scoring_requests ORDER BY received_at DESC LIMIT 5;"

docker compose exec db psql -U credit_user -d credit_risk -c `
  "SELECT request_id, default_probability, risk_band, created_at FROM scoring_predictions ORDER BY created_at DESC LIMIT 5;"
```

Если DB/user изменены, используйте значения из `.env`. Объясните one-to-one request /
prediction relation, unique idempotency key и единую transaction.

## 10. Batch scoring

Требует bundle и `data/processed/test_features.parquet`:

```powershell
python -m src.cli batch-score
Get-ChildItem artifacts\predictions,artifacts\reports
```

Online и batch используют один `ScoringService`, input contract, threshold и risk
bands. Не показывайте prediction artifacts как файлы репозитория — они gitignored.

## 11. Drift monitoring

```powershell
python -m src.cli monitor-drift
$drift = Get-Content artifacts\reports\drift_report.json -Raw | ConvertFrom-Json
$drift | Select-Object status,rows_analyzed,critical_feature_count,warning_feature_count
```

Что сказать: PSI/missingness report инициирует investigation, но не автоматический
retraining. Reference statistics взяты только из source-model train rows.

## 12. Как завершить демо

Коротко назовите ограничения:

- random stratified split вместо temporal/out-of-time;
- Kaggle population и локальные metrics не гарантируют production quality;
- reason codes не являются causal или regulatory explanations;
- shared API key, single-host Compose и local artifacts недостаточны для банка;
- перед production нужны data lineage/point-in-time validation, SSO/RBAC, TLS,
  secrets manager, rate limits, external monitoring и fairness review.

Остановка без удаления PostgreSQL volume:

```powershell
docker compose down
```

## 13. Privacy-light offer matching

Примените migration, загрузите только синтетический каталог и откройте Riskline:

```powershell
python -m src.db.migrate
python -m src.cli seed-demo-offers
Start-Process http://localhost:3000/offers
```

Покажите band-only форму, обязательное consent, approximate PTI, coverage/confidence и
отфильтрованные карточки Demo Bank. Паспорт, телефон, адрес, работодатель, документы и
данные БКИ не запрашиваются. Точные transient значения не сохраняются в commercial
event tables и не попадают в structured logs.

Кнопка перехода создаёт идемпотентный `click_id`; demo redirect использует
`example.invalid`. Это не реальная affiliate integration. Подчеркните маркировку
рекламы и формулировки: сервис не принимает кредитных решений, финальное решение
принимает банк.

## 14. Postback-learning loop

Для локальной проверки задайте отдельный `PARTNER_POSTBACK_SECRET`. Partner payload
подписывается HMAC-SHA256 по canonical JSON и нормализуется в band/status fields.
Secret и raw payload не показывайте и не коммитьте.

```powershell
python -m src.cli build-offer-ranking-dataset
python -m src.cli train-offer-ranker
python -m src.cli evaluate-offer-ranker
```

Без достаточного числа реальных events ожидается `insufficient_data`. Это корректный
promotion gate: production default остаётся `OFFER_RANKER_MODE=rules`.
