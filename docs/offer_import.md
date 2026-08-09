# Безопасный импорт офферов

CLI импортирует операторский каталог из YAML или CSV без сохранения приватных
affiliate URL и токенов в Git или базе данных. В каталоге хранится только имя
переменной окружения, например `ALFA_CREDIT_AFFILIATE_TEMPLATE`. Сам шаблон URL
разрешается из environment непосредственно перед tracked redirect.

## Формат YAML

```yaml
offers:
  - bank_id: alfa
    product_name: Consumer credit
    product_type: cash_loan
    is_active: true
    priority: 50
    min_amount: 50000
    max_amount: 1000000
    min_term_months: 6
    max_term_months: 60
    allowed_age_bands: [25_34, 35_44, 45_54]
    allowed_regions: [all]
    allowed_employment_types: [employee]
    allowed_credit_history_bands: [good, limited]
    max_pti_band: medium
    risk_band_policy: [low, medium]
    advertiser_name: Example advertiser
    ad_label_text: "Реклама"
    erid: null
    legal_disclaimer: "Финальное решение принимает банк."
    full_cost_range_text: null
    compensation_disclosure: "Сервис может получить вознаграждение за переход."
    partner_terms_url: https://partner.example/credit-terms
    main_benefit: "Подходит по сумме и сроку"
    display_warnings:
      - "Условия определяет партнёр"
    cta_text: "Посмотреть условия"
    partner_id: future_partner
    affiliate_url_template_key: ALFA_CREDIT_AFFILIATE_TEMPLATE
    commission_type: fixed
    commission_amount: 1000
    expires_at: 2027-12-31T23:59:59Z
```

CSV использует те же имена колонок. Списки задаются через `|`, например
`25_34|35_44|45_54`. Пара `(bank_id, product_name)` является стабильным ключом:
повторный `--apply` обновляет существующую запись, а дубликаты внутри одного файла
отклоняются.

## Partner configuration

Реальный partner должен быть явно включён в локальной конфигурации и ссылаться только
на имена environment variables:

```yaml
partners:
  future_partner:
    enabled: true
    adapter: env_template
    secret_env: FUTURE_PARTNER_POSTBACK_SECRET
```

Перед импортом задайте значения только в environment или ignored `.env`:

```powershell
$env:FUTURE_PARTNER_POSTBACK_SECRET = "<strong-local-secret>"
$env:ALFA_CREDIT_AFFILIATE_TEMPLATE = "<private-template-with-click_id-placeholder>"
```

Ни CLI, ни validation error не печатают значения этих переменных.

## Команды

Сначала всегда выполняйте dry-run:

```powershell
python -m src.cli import-offers --path C:\secure\offers.yaml --dry-run
python -m src.cli import-offers --path C:\secure\offers.csv --dry-run
```

После успешной проверки примените upsert и при необходимости сформируйте безопасный
операторский export:

```powershell
python -m src.cli import-offers --path C:\secure\offers.yaml --apply
python -m src.cli export-offers --path artifacts/reports/offers_export.csv
```

Export содержит `affiliate_url_template_key`, но никогда не содержит разрешённый
URL template или secret. `artifacts/reports/` игнорируется Git.

## Проверки

Импорт отклоняет отсутствующие данные рекламодателя, рекламную маркировку,
юридический текст или раскрытие возможного вознаграждения, некорректные диапазоны,
просроченный активный оффер, дубликаты и реальный активный оффер без template key
или публичной HTTPS-ссылки на условия партнёра. Если в видимом тексте указана ставка,
обязателен `full_cost_range_text`. Отсутствующий ERID не подменяется вымышленным:
оператор получает предупреждение и должен проверить маркировку до публикации.

URL с token/secret/query-параметрами, выключенный или неправильно настроенный partner
и секретные значения непосредственно в import-файле отклоняются. Исключение сделано
только для `partner_terms_url`: это публичная HTTPS-ссылка без query, fragment и credentials.
Публичный API не возвращает commission, template key, validation flags, ссылку на условия
партнёра или внутренние ranking components.
