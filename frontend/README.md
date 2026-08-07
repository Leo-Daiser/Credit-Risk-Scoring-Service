# Riskline operator console

React/Vinext кабинет для Credit Risk Scoring Service.

## Что реализовано

- dashboard по online-решениям и batch jobs;
- одиночный скоринг через JSON feature payload;
- загрузка CSV/parquet в durable очередь;
- скачивание шаблона и готового prediction-only CSV;
- история решений без показа чувствительного payload;
- экран model bundle и input contract;
- server-side BFF: `API_KEY` не передаётся в браузер.

Frontend не хранит продуктовые данные в browser storage. Источником истины
остаются FastAPI, PostgreSQL и artifact storage backend-контура.

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
