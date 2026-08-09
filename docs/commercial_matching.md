# Privacy-light credit offer matching

## Назначение

Riskline предоставляет предварительный расчёт и подбор кредитных предложений.
Публичный поток построен как: локальный расчёт → минимальный профиль → краткий
результат → рекомендованное предложение → прозрачный отслеживаемый переход.
Сервис не принимает кредитных решений и не
предсказывает решение конкретного банка. Он использует введённые пользователем
диапазоны, оценивает примерную нагрузку, исключает явно неподходящие предложения и
ранжирует оставшиеся.

## Conversion и recommendation boundary

Рекомендация остаётся fit-first. Жёсткая совместимость проверяется до ранжирования.
Платёж, долговая нагрузка, сумма/срок, цель и полнота данных определяют основной
порядок. Коммерческие сигналы могут разрешать только близкие по качеству варианты
выше настроенного порога; использование такого tie-breaker записывается во внутреннюю
аналитику.

Каждая публичная CTA сначала вызывает tracked click endpoint. После успешной записи
клика пользователь видит прозрачный экран перехода: условия и решение определяет
партнёр, переход учитывается в аналитике, Riskline может получить вознаграждение.
Прямые неотслеживаемые CTA не отображаются.

## Offer disclosure contract

Активный оффер содержит рекламодателя, рекламную пометку, юридический текст,
compensation disclosure, разрешённый CTA и tracked redirect. Real-partner оффер также
требует публичный HTTPS URL условий и env-key reference для приватного affiliate
template. Если display copy содержит ставку, обязателен текст диапазона полной
стоимости. Отсутствующий ERID не выдумывается и создаёт operator warning.

## Архитектура

```text
короткий анонимный профиль
  -> approximate annuity + PTI
  -> адаптер текущего credit-risk bundle
       `-> unknown/low coverage без имитации полного score
  -> прозрачные eligibility rules
  -> deterministic ranker (production default)
  -> impression -> tracked click -> signed partner postback
  -> analytics/quality/segment loop
  -> offline ranking dataset -> optional ML ranker
```

Credit-risk модель и offer ranker решают разные задачи. Первая оценивает риск дефолта
в терминах Home Credit population. Вторая должна в будущем оценивать outcome
конкретного предложения по фактическим impression/click/application/approval/issued
событиям. Риск дефолта не является вероятностью одобрения.

## Компоненты

- `src/offers/affordability.py` — консервативные оценки диапазонов, аннуитет и PTI;
- `src/offers/risk_profile.py` — ограниченный адаптер bundle с безопасной деградацией;
- `src/offers/eligibility.py` — блокирующие и мягкие правила с reason codes;
- `src/offers/ranking.py` — rules formula и opt-in загрузка ML artifact;
- `src/offers/revenue.py` — conservative priors, smoothed history и revenue proxy;
- `src/offers/analytics.py` — funnel, CTR, conversion и recorded revenue aggregates;
- `src/offers/quality.py` — operator flags для copy/rules/partner data;
- `src/offers/segment_analysis.py` — privacy-light underserved segment report;
- `src/offers/experiments.py` — deterministic session-hash assignment;
- `src/offers/partners/` — интерфейс partner adapter и demo-реализация;
- `src/offers/service.py` — транзакции profile/impression/click/postback;
- `src/offers/training_dataset.py` — одна строка на impression без row explosion;
- `src/offers/train_offer_ranker.py` — group split по profile и data sufficiency gate;
- `src/api/commercial_routes.py` — versioned HTTP contract;
- `frontend/app/offers` — отдельный privacy-light flow, не смешанный с operator scoring.

## API

- `POST /v1/profile/score` — preliminary profile без записи полного payload;
- `POST /v1/offers/match` — profile, eligibility, ranking и impression events;
- `GET /v1/offers` — только публичные поля активных предложений;
- `POST /v1/offers/{offer_id}/click` — уникальный click и partner URL;
- `POST /v1/partner/postback` — HMAC-SHA256, нормализованные outcome fields и
  идемпотентность по `postback_id` либо `(click_id, status)`.
- `GET /v1/analytics/commercial-summary` — internal funnel/revenue aggregates;
- `GET /v1/offers/quality-report` — internal offer quality diagnostics;
- `GET /v1/analytics/segment-opportunities` — internal underserved segments;
- `GET /v1/analytics/event-debug` — click/postback metadata без raw payload.

`/v1/profile/score` сохраняет только безопасные funnel event types, но не профильный
payload. `/v1/offers/match` сохраняет band-level профиль и связанные impression events. Partner endpoint
использует отдельный `PARTNER_POSTBACK_SECRET`, а не browser API key.

## Ранжирование

До появления достаточных outcome data production default — `OFFER_RANKER_MODE=rules`:

```text
0.28 fit + 0.22 affordability + 0.18 risk compatibility
+ 0.14 product match + 0.10 commercial priority + 0.08 expected revenue proxy
```

Expected revenue proxy использует click/approval/issue priors и нормализованный
commission proxy. История сглаживается; demo commission не влияет на порядок. При
плохом fit commercial/revenue components дополнительно ограничиваются. Ineligible
offer никогда не попадает в ranker. Public response не содержит weights, commission
или revenue breakdown.
При `OFFER_RANKER_MODE=ml` сервис загружает только versioned local artifact. Если
артефакт отсутствует или несовместим, запрос не падает: используется rules fallback с
явным warning.

## Monetization и learning loop

Demo catalog содержит только `Demo Bank A/B/C` и домен `example.invalid`. Для реального
партнёра affiliate template загружается из защищённой конфигурации/БД; приватные
токены нельзя коммитить. Outcome labels строятся из подписанных postback:
`clicked`, `application_started`, `application_submitted`, `approved`, `issued` и
`commission_amount`.

Реальный ranker допустим только после проверки sample size, temporal stability,
calibration, top-k/segment metrics и bias/compliance review. Synthetic data подходит
для теста pipeline, но не для заявления о production-качестве.

## Безопасный импорт каталога

Оператор импортирует YAML/CSV через `python -m src.cli import-offers`. Dry-run
выполняет полную валидацию без записи, `--apply` делает детерминированный upsert по
`(bank_id, product_name)`. В Git и БД сохраняется только
`affiliate_url_template_key`; приватный template разрешается из environment во
время tracked click. Export также не содержит разрешённые URL или secrets. Полный
формат и операционный порядок описаны в [offer_import.md](offer_import.md).

## Analytics и experiment loop

Request-level `commercial_funnel_events` хранит только event type, band dimensions,
anonymous IDs и variant. Impression/click/postback не дублируются: аналитика читает
существующие нормализованные таблицы. Воронка покрывает profile start/completion,
score, match request, shown/no-offer, click, application outcomes, issued и recorded
revenue. Raw profile и raw postback body в analytics storage отсутствуют.

Публичная воронка проходит через landing, browser-only calculator, consent-gated
privacy-light form, result summary, offer cards и tracked click. Browser events
принимаются отдельным allowlisted endpoint без exact financial values; match/result
events формируются сервером из уже нормализованных bands. Public response объясняет
совместимость, но не раскрывает commission, revenue proxy, weights или raw rules.

Эксперимент назначается детерминированно по hash `anonymous_session_id`. По умолчанию
`configs/experiments.yaml` выключен и 100% трафика использует `rules_v1`. Варианты
меняют только ограниченные fit/revenue multipliers; eligibility остаётся неизменным.
Experiment metrics являются продуктовой аналитикой, а не метриками банковского
одобрения.

## Partner abstraction и защита

`PartnerAdapter` разделяет affiliate URL, HMAC verification, postback normalization и
public disclosure. В репозитории реализован только `DemoPartnerAdapter`; реальные
network adapters, credentials и external calls отсутствуют. `configs/partners.yaml`
содержит только названия env variables. Enabled non-demo partner без secret считается
configuration error.

Public commercial endpoints защищены single-process sliding-window limiter. Он
подходит для local/demo, но не синхронизируется между репликами. Публичный deployment
обязан добавить reverse proxy/WAF или Redis-backed rate limiting. Operator analytics
fail closed без server-side API key и доступны frontend только через BFF.

## Ограничения

- PTI приблизительный, не нормативный и не учитывает все расходы/страховки;
- короткий профиль покрывает малую часть 622-feature bundle;
- Home Credit population не соответствует конкретному российскому банку;
- demo offers не являются реальными продуктами;
- автоматическое удаление событий по retention schedule пока не реализовано;
- юридические тексты являются инженерной границей, а не юридическим заключением.
