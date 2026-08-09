# Riskline

Riskline — сервис предварительного расчёта платежа, оценки долговой нагрузки и
подбора кредитных предложений партнёров. Публичный поток использует примерные
диапазоны и не требует паспорта, телефона, документов, точного адреса или данных БКИ.

Сервис не принимает кредитных решений. Финальное решение и индивидуальные условия
определяет банк или иной кредитный партнёр. Рекламные предложения маркируются, а
партнёрские переходы учитываются для аналитики и атрибуции.

## Возможности

- браузерный калькулятор платежа, переплаты, остатка бюджета и долговой нагрузки;
- минимальная анкета для предварительного подбора;
- fit-first ранжирование совместимых предложений;
- обязательная рекламная маркировка и прозрачный переход к партнёру;
- отслеживаемые переходы и подписанные партнёрские события;
- аналитика воронки, выручки, качества предложений и неудовлетворённого спроса;
- защищённое управление предложениями без размещения партнёрских секретов в Git;
- раздельные режимы `local`, `demo` и `public`.

## Публичный поток

1. Пользователь рассчитывает ориентировочный платёж локально в браузере.
2. Указывает только примерные диапазоны и подтверждает обработку данных.
3. Получает краткое резюме и совместимые предложения.
4. Сравнивает причины рекомендации и предупреждения.
5. Переходит к партнёру через отслеживаемый redirect.

Комиссии, внутренние веса, шаблоны партнёрских ссылок и технические причины
фильтрации публичному клиенту не возвращаются.

## Локальный запуск

Требования: Python 3.11+, Node.js 20+, PostgreSQL 16 или Docker.

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m src.db.migrate
python -m src.cli setup-demo
uvicorn src.api.main:app --reload
```

В отдельном терминале:

```powershell
cd frontend
npm ci
npm run dev
```

Публичный интерфейс: `http://localhost:3000`.

## Docker demo

```powershell
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build
python -m src.cli verify-demo
python scripts/smoke_public_demo.py --base-url http://localhost:8000 --frontend-url http://localhost:3000 --mode demo
```

Демо-предложения синтетические и явно помечаются в интерфейсе. Они не являются
актуальными банковскими продуктами.

## Управление предложениями

Операторский интерфейс `/operator/offers` доступен только в разрешённых local/demo
режимах и через серверную границу авторизации. Он поддерживает создание,
редактирование, предварительную проверку и деактивацию предложений.

Партнёрский URL хранится только в переменной окружения. В базе и импортируемых
файлах используется ссылка на имя переменной, например:

```text
ALFA_CREDIT_AFFILIATE_TEMPLATE
```

Поддерживается безопасный импорт:

```powershell
python -m src.cli import-offers --path path/to/offers.yaml --dry-run
python -m src.cli import-offers --path path/to/offers.yaml --apply
python -m src.cli export-offers --path artifacts/reports/offers_export.csv
```

Подробности: [управление импортом](docs/offer_import.md) и
[партнёрский контур](docs/commercial_matching.md).

## Проверки

Backend:

```powershell
pytest -q
ruff check src tests migrations scripts
python -m pip check
pip-audit -r requirements.txt
```

Frontend:

```powershell
cd frontend
npm ci
npm run lint
npx tsc --noEmit
npm test
npm run build
```

Compose:

```powershell
docker compose config --quiet
docker compose -f docker-compose.yml -f docker-compose.demo.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.public.example.yml config --quiet
```

## Развёртывание и безопасность

- [Переменные окружения](docs/env_reference.md)
- [Demo-развёртывание](docs/deployment_demo.md)
- [Проверка публичного размещения](docs/deployment_public_checklist.md)
- [Матрица доступа](docs/endpoint_access_matrix.md)
- [Операционные процедуры](docs/operations.md)
- [Контракт минимальных данных](docs/privacy_light_data_contract.md)
- [Рекламная маркировка](docs/ad_disclosure.md)

В режиме `public` операторские страницы, документация сервера, метрики и
диагностические endpoints закрываются. Публичное размещение требует сильных
секретов, TLS, reverse proxy/WAF, внешнего rate limiting и юридической проверки
рекламных материалов.

## Ограничения

- предварительный подбор не заменяет банковскую проверку;
- без БКИ и документов уверенность результата ограничена;
- правила рекламной маркировки и полная стоимость должны проверяться для каждого
  реального партнёра и юрисдикции;
- встроенный rate limiter предназначен для одного процесса;
- данные партнёрских событий необходимы до включения обучаемого ранжирования;
- реальные партнёрские секреты, исходные данные и артефакты расчётного модуля не
  должны попадать в Git или Docker build context.

## Лицензия

MIT.
