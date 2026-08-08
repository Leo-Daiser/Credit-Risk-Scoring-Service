# ML report

## 1. Бизнес-задача

Сервис оценивает вероятность того, что заявитель допустит дефолт по кредиту.
Вероятность используется как risk signal: поверх неё применяется настраиваемый
operating threshold. Это учебная постановка credit scoring, а не юридически значимое
кредитное решение.

## 2. Данные и target

Источник — Home Credit Default Risk. Основная train table содержит одну строку на
заявку (`SK_ID_CURR`). `TARGET=1` означает клиента с проблемами погашения, `TARGET=0`
— отсутствие такого события в разметке соревнования.

Feature pipeline использует восемь таблиц:

1. `application_train` и `application_test` — заявка, доход, кредит, аннуитет,
   демография и внешние score features.
2. `bureau` — кредиты клиента в других организациях.
3. `bureau_balance` — месячная история bureau accounts.
4. `previous_application` — предыдущие заявки в Home Credit.
5. `POS_CASH_balance` — POS/CASH contract history.
6. `installments_payments` — сроки и суммы платежей.
7. `credit_card_balance` — balance, utilization, drawings и delinquency.

History tables агрегируются до одной строки на `SK_ID_CURR`: counts, ratios,
missingness-aware numeric statistics, status shares, delinquency и payment features.
Финальный builder проверяет уникальность applicant key, согласует train/test schema,
удаляет почти полностью пустые и constant columns.

## 3. Validation strategy

Текущая реализация использует deterministic stratified split с seed `42`:

```text
full labelled data
  -> 80% source-model train
  -> 20% holdout
       -> 50% calibration + threshold selection
       `-> 50% final evaluation
```

В локальном полном прогоне это 246 008 train rows, 30 751 calibration rows и
30 752 evaluation rows. Source CatBoost и baseline обучены на одинаковой 80%
train-части. Production packaging проверяет совпадение seed, holdout fraction и
feature count с manifests исходных моделей.

Evaluation half не используется кодом calibration, threshold selection или reference
statistics. Однако это random split, не out-of-time validation. Кроме того, полный
20% challenger holdout доступен в intermediate training reports, поэтому многократная
ручная настройка модели по этим отчётам могла бы косвенно переобучить model choice.
Для реального production нужен отдельный development/validation/test protocol и
закрытый temporal holdout.

## 4. Baseline

Logistic Regression даёт интерпретируемую линейную точку отсчёта. Pipeline включает:

- median imputation и scaling numeric features;
- explicit missing handling и one-hot encoding categoricals;
- `class_weight=balanced` для дисбаланса target;
- фиксированный seed и сохраняемый preprocessing вместе с estimator.

На тех же final evaluation rows baseline получил ROC-AUC `0.78459` и PR-AUC
`0.28107`. Эти значения относятся только к локальному прогону.

## 5. CatBoost challenger

CatBoost выбран как nonlinear challenger для mixed-type tabular data. Он моделирует
взаимодействия и нелинейности без ручного one-hot расширения категориальных признаков,
обрабатывает missing values и подходит для большого числа агрегированных credit
features.

Конфигурация локального прогона: 500 trees, depth 7, learning rate 0.05,
`auto_class_weights=Balanced`, L2 regularization 5. На полном intermediate 20%
holdout до production calibration challenger получил ROC-AUC `0.78906` и PR-AUC
`0.28855`. Это diagnostic metric, а не final test result.

## 6. Calibration

Source estimator замораживается, а sigmoid calibrator обучается только на calibration
half. Calibration не меняет ranking metrics, но переводит score в более пригодную для
decision policy вероятность.

На final evaluation split Brier score изменился с `0.17250` до `0.06544`, а ECE —
с `0.29711` до `0.00351`. Результат сильный для конкретного локального split, но не
гарантирует calibration на другом population.

## 7. Threshold selection

Threshold выбирается только по calibration half из заданной grid. Политика минимизирует
ожидаемую стоимость при `false_negative_cost=5`, `false_positive_cost=1` и требует:

- recall не ниже `0.45`;
- predicted-positive rate не выше `0.25`.

Локально выбран threshold `0.15`. После выбора он один раз применяется к final
evaluation half. Costs — демонстрационные бизнес-параметры, а не оценённая банковская
экономика.

## 8. Финальные локальные метрики

Все значения ниже получены локально для bundle
`catboost_calibrated-6dba880cb73a` на 30 752 final evaluation rows.

| Metric | Calibrated CatBoost |
|---|---:|
| ROC-AUC | 0.79233 |
| ROC-AUC 95% bootstrap CI | 0.78272–0.80081 |
| PR-AUC | 0.29791 |
| PR-AUC 95% bootstrap CI | 0.27858–0.31985 |
| Brier score | 0.06544 |
| ECE | 0.00351 |
| Recall @ 0.15 | 0.52880 |
| Precision @ 0.15 | 0.25760 |
| F1 @ 0.15 | 0.34644 |
| ROC-AUC delta vs baseline | +0.00774 |
| Paired 95% CI for delta | +0.00391…+0.01165 |

Configured acceptance gates для этого локального bundle прошли. Gates защищают
pipeline от заведомо слабого artifact, но не являются внешней сертификацией модели.

## 9. Почему важны PR-AUC, Brier и ECE

Target несбалансирован: в локальном dataset positive rate около 8%. ROC-AUC полезен
для ranking, но может выглядеть приемлемо при слабом качестве редкого positive class.
PR-AUC сильнее фокусируется на precision/recall для дефолтов и сравнивается с base
rate, поэтому она обязательна рядом с ROC-AUC.

Brier score измеряет среднюю квадратичную ошибку вероятности: уверенная неправильная
оценка штрафуется сильнее. ECE сравнивает predicted probability с observed frequency
по bins. Они нужны, потому что threshold, expected cost и risk bands используют
численную вероятность, а не только порядок клиентов.

## 10. Leakage prevention

- `TARGET` и `SK_ID_CURR` исключаются из feature matrix.
- History tables агрегируются до applicant level до merge, что предотвращает row
  explosion и дублирование target rows.
- Train/test feature schemas согласуются детерминированно.
- Source model не обучается на holdout rows.
- Calibrator и threshold используют calibration half; final metrics — evaluation half.
- Baseline и candidate сравниваются на одних evaluation rows paired bootstrap-методом.
- Drift reference distributions строятся только по source-model train rows.
- Bundle связывает SHA-256 fingerprints data, models, schema, config, packaging code и
  pinned dependencies.

## 11. Ограничения

- Нет temporal/out-of-time и external validation.
- Kaggle population и label definition не равны текущему банковскому production.
- Нет point-in-time feature store; доступность каждого history field на момент заявки
  должна быть отдельно подтверждена перед реальным использованием.
- Dataset shift измеряется offline PSI/missingness report, без automated retraining.
- Subgroup report не является полноценным fairness или regulatory analysis.
- SHAP reason codes описывают поведение модели, но не причинность и не законное
  основание отказа.
- Costs, risk bands и threshold требуют владельца бизнес-политики и регулярной
  revalidation.
