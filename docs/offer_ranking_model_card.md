# Offer ranking model card

## Назначение

Optional offer ranker ранжирует уже допустимые предложения. Он не оценивает
кредитоспособность, не принимает решение банка и не заменяет eligibility rules.
Production default — deterministic rules.

## Данные и labels

Одна строка датасета соответствует одному `offer_impression`. Profile features —
только bands и diagnostics; offer features — product type, bank/demo ID, priority,
показанный rank и rules score. Labels: click, application start/submission, approval,
issue и commission. Dataset builder агрегирует clicks/postbacks до пары
profile/offer, поэтому join не размножает impression rows.

## Training contract

Trainer использует `HistGradientBoostingClassifier` с one-hot preprocessing,
минимальный sample gate и group split по `profile_id`. Target выбирается из
`clicked_flag`, `approved_flag`, `issued_flag`. Нужны минимум настроенное число строк и
оба класса в train/evaluation partitions. При недостатке данных создаётся только
`insufficient_data` report; production artifact не создаётся.

## Метрики

Сохраняются ROC-AUC, PR-AUC, log loss, calibration bins, CTR/approval/issued@1/3/5,
expected revenue@k и segment summaries по risk/PTI/income bands. Для реального запуска
нужны temporal holdout, confidence intervals и сравнение с rules baseline. Текущий
group split — защита от прямого profile leakage, но не замена out-of-time validation.

## Privacy, fairness и ограничения

Модель не получает identity/documents/BKI. Band design снижает детализацию, но не
устраняет proxy bias. До production promotion требуются segment stability, adverse
impact/fairness review, мониторинг no-offer rate и ручное утверждение feature/target
policy. Revenue metric не должна быть единственным promotion criterion.

Synthetic fixtures подтверждают только работоспособность pipeline. Они не являются
реальными outcome data и не дают основания включать ML mode в production.
