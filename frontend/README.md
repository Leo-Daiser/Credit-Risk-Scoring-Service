# Riskline operator console

React/Vinext кабинет для Credit Risk Scoring Service.

## Что реализовано

- dashboard по online-решениям и batch jobs;
- пользовательский кредитный калькулятор с локальным расчётом платежа и бюджета;
- opt-in ML-оценка по короткой анкете и экспертный скоринг через JSON feature payload;
- загрузка CSV/parquet в durable очередь;
- скачивание шаблона и готового prediction-only CSV;
- история решений без показа чувствительного payload;
- экран model bundle и input contract;
- server-side BFF: `API_KEY` не передаётся в браузер.

Frontend не хранит продуктовые данные в browser storage. Источником истины
остаются FastAPI, PostgreSQL и artifact storage backend-контура.

Калькулятор платежа работает в браузере и не отправляет данные. ML-оценка
запускается отдельной кнопкой после явного подтверждения: тогда поля анкеты и
результат сохраняются backend-сервисом в PostgreSQL audit log. Короткая анкета
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
