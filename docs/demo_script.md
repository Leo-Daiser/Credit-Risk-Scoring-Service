# Commercial matching demo

## Подготовка

```powershell
Copy-Item .env.example .env
docker compose up -d db
python -m src.db.migrate
python -m src.cli seed-demo-offers
uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

В другом PowerShell:

```powershell
Set-Location frontend
npm run dev
```

Откройте `http://localhost:3000/offers`. Покажите band-only форму, обязательное consent,
preliminary PTI, confidence и demo offer cards. Подчеркните, что risk bundle может быть
недоступен/низкопокрыт, но matching деградирует безопасно.

Tracked click создаётся кнопкой «Перейти». Demo URL использует `example.invalid` и не
является реальной интеграцией. Для postback сформируйте canonical JSON и HMAC-SHA256 с
локальным `PARTNER_POSTBACK_SECRET`; не показывайте secret на экране и не коммитьте его.

После накопления synthetic test events:

```powershell
python -m src.cli build-offer-ranking-dataset
python -m src.cli train-offer-ranker
python -m src.cli evaluate-offer-ranker
```

При недостатке строк ожидаемый результат — `insufficient_data`. Это корректный gate,
а не ошибка demo. Generated parquet/model/metrics/reports находятся в gitignored
`data/processed` и `artifacts`.
