# Privacy-light credit offer matching

## Назначение

Commercial extension превращает скоринг из изолированной ML-демонстрации в сервис
предварительного подбора кредитных предложений. Сервис не одобряет кредит и не
предсказывает решение конкретного банка. Он использует введённые пользователем
диапазоны, оценивает примерную нагрузку, исключает явно неподходящие предложения и
ранжирует оставшиеся.

## Архитектура

```text
короткий анонимный профиль
  -> approximate annuity + PTI
  -> адаптер текущего credit-risk bundle
       `-> unknown/low coverage без имитации полного score
  -> прозрачные eligibility rules
  -> deterministic ranker (production default)
  -> impression -> tracked click -> signed partner postback
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

`/v1/profile/score` вычисляет результат без долговременной записи. `/v1/offers/match`
сохраняет только band-level профиль и связанные impression events. Partner endpoint
использует отдельный `PARTNER_POSTBACK_SECRET`, а не browser API key.

## Ранжирование

До появления достаточных outcome data production default — `OFFER_RANKER_MODE=rules`:

```text
0.30 user fit + 0.25 affordability fit + 0.20 risk compatibility
+ 0.15 product match + 0.10 commercial priority
```

Затем применяется penalty за низкую полноту профиля. Commission не входит в формулу
напрямую и не может вернуть в выдачу предложение, заблокированное eligibility rules.
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

## Ограничения

- PTI приблизительный, не нормативный и не учитывает все расходы/страховки;
- короткий профиль покрывает малую часть 622-feature bundle;
- Home Credit population не соответствует конкретному российскому банку;
- demo offers не являются реальными продуктами;
- автоматическое удаление событий по retention schedule пока не реализовано;
- юридические тексты являются инженерной границей, а не юридическим заключением.
