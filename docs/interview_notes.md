# Interview notes

## Почему нельзя бездумно использовать random split

В credit scoring случайный split может смешать разные временные режимы, продукты или
повторных клиентов и дать оптимистичную оценку. Текущий Home Credit MVP использует
stratified random split, потому что в pipeline нет надёжного application timestamp для
out-of-time protocol. Это честно обозначенное ограничение. В production я бы применил
temporal split, group constraints для связанных клиентов/contracts и внешний holdout.

## Как защищены calibration и evaluation

Сначала детерминированно восстанавливается тот же 80/20 split, на котором обучены
source models. Source CatBoost заморожен. Holdout делится пополам:

- calibration half обучает sigmoid calibrator и выбирает threshold;
- evaluation half используется только для final metrics, bootstrap intervals,
  baseline comparison, subgroup report и acceptance gates.

Seed, holdout size и feature count сверяются с source/baseline metrics manifests.
Train-only rows используются для drift reference. Ограничение: intermediate model
reports содержат metrics на полном 20% holdout, поэтому process discipline всё равно
нужна, чтобы не tuning-ить model choice по final-like rows.

## Почему CatBoost подходит для tabular credit scoring

- поддерживает numeric/categorical features и missing values;
- моделирует нелинейности и interactions, которых нет в Logistic Regression;
- устойчив на heterogeneous applicant/history aggregates;
- даёт feature importance и local SHAP values;
- работает как sklearn-compatible pipeline и сериализуется вместе с preprocessing.

Это не означает, что CatBoost всегда лучший. Его преимущество подтверждается только
на конкретных validation data; baseline остаётся необходимой точкой сравнения.

## Что означают reason codes

Для CatBoost это крупнейшие положительные local SHAP contributions, увеличившие model
score для конкретного request. Для linear fallback — положительные contributions в
log-odds. Они объясняют вычисление модели локально.

Они не доказывают причинность, не являются counterfactual explanation, не гарантируют
fairness и не должны автоматически становиться формулировкой отказа клиенту.

## Как работает model versioning

Bundle содержит `artifact_inputs` с SHA-256 для:

- source/baseline models и metrics;
- training parquet;
- feature schema и production config;
- packaging/evaluation code;
- pinned production dependencies.

Canonical manifest хэшируется, первые 12 hex symbols входят в `model_version`.
Runtime повторно проверяет manifest, schema, threshold, risk bands и bundle format.
Это идентификация и integrity contract, но не digital signature или provenance proof.

## Как валидируется API input

Pydantic ограничивает request envelope, request ID, число features, строки и
нефинитные значения. Затем bundle contract:

1. отклоняет неизвестные feature names;
2. приводит numeric fields и отклоняет нечисловые/бесконечные values;
3. требует configured keys;
4. проверяет minimum non-null coverage;
5. выравнивает columns в training order;
6. сообщает out-of-range numeric и unseen categories как diagnostics.

Required keys и coverage принадлежат versioned bundle, поэтому online и batch не
расходятся.

## Как работает PostgreSQL audit logging

При первом использовании version регистрируется в `model_registry`. Затем request
payload и model version записываются в `scoring_requests`, а probability/risk band /
reason codes — в `scoring_predictions`. Операции выполняются одной transaction.

Duplicate `request_id` даёт `409`. Integrity/database error вызывает rollback. При
`DATABASE_REQUIRED=true` scoring не возвращает успешный response, если audit record
не сохранён. Feature payload хранится в DB, но исключён из application logs.

## Зачем PR-AUC при наличии ROC-AUC

При ~8% positive class ROC-AUC может выглядеть приемлемо даже при слабой precision по
дефолтам. PR-AUC показывает trade-off precision/recall вокруг редкого positive class
и должна сравниваться с prevalence baseline. Нужны обе метрики: ROC-AUC для ranking по
всем парам, PR-AUC для качества обнаружения дефолтов.

## Зачем calibration metrics

Threshold, expected cost и risk bands используют абсолютное значение probability.
ROC-AUC/PR-AUC не отвечают, соответствует ли score `0.20` приблизительно 20% observed
risk. Brier score измеряет probability error, ECE — расхождение predicted/observed
frequency по bins. Calibration должна повторно проверяться после population shift.

## Что улучшить в реальном production

- temporal/out-of-time и external validation;
- point-in-time correct feature computation и data lineage;
- fairness, stability и regulatory review по защищённым группам;
- signed artifact registry, object storage и controlled promotion;
- SSO/RBAC, TLS, secrets manager, rate limits и network policies;
- async/replicated serving после реального load profile;
- online feature/input drift, outcome monitoring и delayed-label evaluation;
- rollback policy, model champion/challenger governance и retraining approval;
- encryption, retention и access audit для feature payloads в PostgreSQL.

Главная позиция на интервью: проект демонстрирует инженерные контракты и честные
границы portfolio MVP, а не имитирует готовность к банковскому production.

## Чем PD model отличается от approval/offer model

Текущий CatBoost оценивает default risk на Home Credit label. Решение конкретного
банка дополнительно зависит от его policy, fraud/KYC, БКИ, pricing и лимитов. Поэтому
PD score нельзя называть approval probability. Короткий профиль дополнительно имеет
ограниченное feature coverage, которое сервис показывает явно.

## Зачем нужны partner postback outcomes

Без impression/click/application/approval/issued данных нельзя обучить ranker под
реальную partner funnel. Click измеряет интерес, approval — policy fit, issued —
финальный outcome. Labels имеют разную задержку и selection bias; synthetic fixtures
подтверждают только работоспособность pipeline.

## Как устроен privacy-light matching

Frontend принимает диапазоны и отдельные consent. БД хранит band snapshot, hashes и
нормализованные outcomes. Identity, документы и БКИ отсутствуют. Eligibility сначала
блокирует несовместимые offers, затем rules ranker отдаёт 90% веса fit/affordability/
risk/product и 10% commercial priority. Commission не может вернуть заблокированный
offer.

## Как появляется монетизация и обучающие данные

Tracked click связывает анонимный profile и offer, signed postback добавляет outcome и
commission. Этот loop создаёт датасет для будущего ranker. В репозитории используются
только Demo Bank и `example.invalid`, поэтому реальная partner economics не заявлена
как реализованная.
