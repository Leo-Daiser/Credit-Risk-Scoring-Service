# Privacy-light data contract

## Собираемые данные

Публичный matching contract принимает только диапазоны: возраст, доход, текущие
платежи, запрашиваемую сумму, тип занятости, кредитную историю, цель, срок и
необязательный регион. Точная сумма кредита и точный текущий платёж допускаются API
как transient inputs, но frontend их не запрашивает и БД их не хранит.

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

Frontend собирает band-only форму. Annuity/PTI и matching вычисляются на сервере;
операторский калькулятор `/score` остаётся отдельным flow. Exact transient values не
попадают в structured logs. Без данных БКИ и полного feature contract confidence
ограничен и показывается пользователю.

Документ фиксирует инженерные границы и не является юридической консультацией.
