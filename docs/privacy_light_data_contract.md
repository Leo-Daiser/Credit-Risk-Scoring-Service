# Privacy-light data contract

## Собираемые данные

Публичный matching contract принимает только диапазоны: возраст, доход, текущие
платежи, запрашиваемую сумму, тип занятости, кредитную историю, цель, срок и
необязательный регион. Точная сумма кредита и точный текущий платёж допускаются API
как transient inputs. Frontend предлагает их только как необязательные поля текущего
matching-запроса; БД их не хранит и browser storage не используется.

Не собираются имя, телефон, паспорт, СНИЛС, ИНН, точный адрес, работодатель,
документы и данные БКИ. Browser storage не используется. В application logs разрешены
только correlation/profile/offer/click IDs, bands, event type и ranker mode.

## Что хранится

`credit_profile_events` содержит band-level snapshot и diagnostics. `offer_impressions`,
`offer_clicks` и `partner_postbacks` содержат нормализованные коммерческие события.
Session key и redirect URL сохраняются только как SHA-256. Raw partner payload не
сохраняется: хранится canonical payload hash. Public offers endpoint исключает
commission и affiliate template.

`PERSIST_EXACT_COMMERCIAL_VALUES=false` зафиксирован как безопасное значение по
умолчанию. Текущая схема вообще не содержит колонок для exact income/payment values;
смена флага сама по себе не расширяет хранение и требует отдельной review/migration.

## Consent и цели обработки

`consent_to_process=true` обязателен для server-side profile/match. Согласие на
рекламную персонализацию отдельное и по умолчанию `false`. Оно не подменяет согласие на
обработку и не делает результат банковским решением.

## Retention

Целевая политика: profile/impression/click events — 90 дней, нормализованные postback —
365 дней, если договор и применимое право не требуют иного. В текущем portfolio MVP
scheduled purge ещё не реализован; оператор обязан удалять данные внешней DB policy.
Это известное ограничение, а не заявленная гарантия.

## Расчёты

Публичный `/score` считает annuity, total repayment, overpayment и PTI полностью в
браузере. Изменение чисел не вызывает backend request; значения не сохраняются.
Privacy-light matching отправляет bands и только явно указанные transient amount/payment,
но persistence сохраняет лишь bands. Exact values не попадают в analytics events или
structured logs. Без данных БКИ и полного feature contract confidence ограничен и
показывается пользователю.

## Public analytics events

Frontend отправляет только allowlisted `landing_viewed`, `calculator_used` и
`calculator_continue_clicked` с названием публичной страницы и ephemeral anonymous
session ID. Matching backend добавляет `profile_started`, `profile_submitted`,
`result_viewed`, `offer_card_viewed` и `no_eligible_offers_viewed` из уже
нормализованного band-only контекста. Event contract запрещает extra fields: точные
суммы, доход, ставка, телефон, email и имя в него не принимаются.

Документ фиксирует инженерные границы и не является юридической консультацией.
