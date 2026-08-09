# Riskline Public Profile Model

## Назначение

`Riskline Public Profile Model` — отдельный consumer-compatible ML-контур. Он
формирует предварительный финансовый профиль, объяснения и входной риск-сигнал для
совместимости и ранжирования офферов. Это не вероятность одобрения, не рейтинг БКИ и
не модель андеррайтинга конкретного российского банка.

Полный `Full Credit Risk Model` с исходной 622-признаковой схемой сохранён для
внутреннего B2B scoring, benchmark и будущих богатых источников данных. Публичный
frontend не зависит от provider-specific названий признаков полного контура.

## Нормализованный контракт

Training и inference используют одну схему: возраст, доход, занятость и стаж,
состав семьи, жильё и собственность, сумма, срок, рассчитанный платёж, текущие
платежи, PTI и производные отношения. Внешний адаптер переводит источник в эту
схему до обучения.

Текущий `HomeCreditPublicTrainingAdapter` использует только легитимно сопоставимые
поля `application_train.csv` и исходную метку риска дефолта. Метки не
синтезируются. Текущие платежи отсутствуют в источнике и поэтому равны нулю в v1;
при публичном inference они входят в PTI и индекс, но это ограничение обязательно
учитывается при интерпретации.

Будущий российский источник должен реализовать преобразование в тот же
`PublicProfileTrainingRow`. API и frontend при замене датасета не меняются.

## Обучение и provenance

```powershell
python -m src.cli build-public-profile-dataset
python -m src.cli train-public-profile-model
```

Конфигурация: `configs/public_profile_model.yaml`. Pipeline сравнивает Logistic
Regression baseline и CatBoost candidate, калибрует выбранную модель и проверяет
acceptance gates. Bundle содержит имя, версию, дату, источник, нормализованную
схему, метрики, risk bands и ограничения популяции.

Generated dataset, bundle, schema и metrics находятся в игнорируемых `data/processed`
и `artifacts/`. Joblib разрешено загружать только из доверенного локального процесса
обучения или контролируемого artifact registry.

Текущая provenance: открытый Home Credit Default Risk dataset, зарубежная
популяция. Нельзя утверждать, что модель обучена на российских заёмщиках или
воспроизводит решение российского банка.

## Riskline Index и объяснения

Riskline Index нормализует откалиброванный модельный сигнал относительно квантилей
validation population и добавляет консервативную поправку на PTI. Значение
округляется до целого и предназначено только для сравнения сценариев внутри
Riskline. Оно не является официальным кредитным score и не равно вероятности
одобрения.

Локальные объяснения строятся однофакторными perturbation относительно training
reference. Публичный ответ содержит только русские labels/messages и стабильные
безопасные codes. Numeric impacts, provider feature IDs и raw probability не
возвращаются.

Actionability policy разрешает рекомендации только по сумме, сроку, текущей
нагрузке и сценарию рефинансирования. Возраст, семейное положение, дети и другие
неизменяемые характеристики не превращаются в советы. Сервис никогда не предлагает
скрывать долг или искажать доход/занятость.

## Runtime и fallback

Artifact: `artifacts/models/public_profile_model_bundle.joblib`. Compose монтирует
каталог моделей read-only из `MODEL_ARTIFACTS_PATH`. `/ready` и защищённый
`/v1/runtime/status` отдельно показывают публичную модель, полную модель, offer
ranker и fallback-only mode.

Если public artifact отсутствует, matching продолжает работать по правилам, но
`model_available=false`, `ml_personalized=false`, индекс отсутствует, а runtime
фиксирует fallback. UI не называет такой результат ML-персонализированным.

## Ограничения и gate замены

- v1 обучена не на российской популяции;
- источник не содержит текущих обязательств и банковского underwriting outcome;
- результат не валидирован как approval model;
- до реального запуска нужна локальная temporal/segment calibration, fairness и
  compliance review;
- замена модели требует сохранения нормализованного input/output contract и новых
  acceptance tests.
