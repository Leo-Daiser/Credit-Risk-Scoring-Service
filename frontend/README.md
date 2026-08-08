# Riskline public MVP and operator console

React/Vinext кабинет для Credit Risk Scoring Service.

## Что реализовано

- dashboard по online-решениям и batch jobs;
- пользовательский кредитный калькулятор с локальным расчётом платежа и бюджета;
- opt-in ML-оценка по короткой анкете и экспертный скоринг через JSON feature payload;
- загрузка CSV/parquet в durable очередь;
- скачивание шаблона и готового prediction-only CSV;
- история решений без показа чувствительного payload;
- экран model bundle и input contract;
- server-side BFF: `API_KEY` не передаётся в браузер;
- В `APP_ENV=public` operator UI и operator BFF-маршруты fail closed; доступен только
  allowlist публичного matching flow.
- Полная матрица доступа: [`../docs/endpoint_access_matrix.md`](../docs/endpoint_access_matrix.md).

Frontend не хранит продуктовые данные в browser storage. Источником истины
остаются FastAPI, PostgreSQL и artifact storage backend-контура.

Публичный калькулятор платежа работает в браузере и не отправляет данные. ML-оценка
доступна только в local/demo operator UI по адресу `/operator/score` и запускается
после явного подтверждения: тогда поля анкеты и результат сохраняются backend-сервисом
в PostgreSQL audit log. Короткая анкета
покрывает только часть полного feature-контракта, поэтому результат показывается как
предварительный и не является кредитным решением или офертой.

## Локальный запуск

Из каталога `frontend`:

```powershell
npm ci
$env:BACKEND_URL = "http://127.0.0.1:8000"
npm run dev
```

Откройте `http://localhost:3000`. Если backend использует ключ:

```powershell
$env:API_KEY = "<local-api-key>"
```

## Проверка

```powershell
npm run lint
npx tsc --noEmit
npm test
```

Полный production-like контур проще запускать из корня через Docker Compose.

## Известная граница зависимостей

`npm audit` сообщает о двух high advisory в транзитивном `image-size@2.0.2`
из `vinext@1.0.0-beta.4`. Исправленной версии в используемой линии Vinext нет;
`npm audit fix --force` предлагает несовместимый downgrade. Пользовательские изображения
runtime не обрабатывает. До обновления Vinext публичный reverse proxy должен также
ограничивать размер HTTP-запроса. Operator UI остаётся выключенным в public mode.
