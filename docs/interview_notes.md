# Commercial extension interview notes

## PD model и approval model

Текущий CatBoost оценивает default risk на Home Credit label. Approval конкретного
банка зависит от его policy, fraud/KYC, БКИ, pricing, лимитов и economics. Поэтому PD
score нельзя называть approval probability. Короткий профиль дополнительно имеет
низкое feature coverage, которое сервис показывает явно.

## Почему нужны postback outcomes

Без impression/click/application/approval/issued данных нельзя обучить ranker под
реальную partner funnel. Click оптимизирует интерес, approval — policy fit, issued —
финальный бизнес outcome. Targets имеют разные delay/bias; production выбор требует
отдельного анализа.

## Privacy-light design

Frontend запрашивает диапазоны и отдельные consent. БД хранит band snapshot, hashes и
нормализованные outcomes. Identity, документы и БКИ отсутствуют. Это уменьшает риск и
трение, но ограничивает точность — trade-off показывается через coverage/confidence.

## Почему ranking не равен максимизации commission

Eligibility сначала блокирует несовместимые предложения. Rules formula отдаёт 90%
веса fit/affordability/risk/product и 10% priority. Commission не является feature
rules ranker. ML promotion требует quality, segment и compliance gates рядом с revenue.

## Как продукт монетизируется

Пользователь получает предварительный профиль и релевантную рекламную выдачу; tracked
click связывает profile/offer, signed postback — outcome/commission. Эта петля создаёт
обучающие данные. В репозитории только demo offers, поэтому реальная интеграция и её
экономика не заявлены как реализованные.
