# Offer ranking model card

## Назначение

Optional offer ranker ранжирует уже допустимые предложения. Он не оценивает
кредитоспособность, не принимает решение банка и не заменяет eligibility rules.
Production default — deterministic rules.

Rules-first pipeline сначала применяет hard eligibility, затем fit-heavy score.
Expected revenue proxy имеет ограниченный вес и не способен вернуть заблокированное
или существенно несовместимое предложение. Demo estimates помечаются `demo_only` и
`low` confidence; public API не показывает commission/revenue internals.

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

## Gate перед включением ML mode

До `OFFER_RANKER_MODE=ml` нужны реальные и point-in-time корректные partner labels,
достаточный sample для обоих классов и out-of-time evaluation. Минимальный набор
сравнений: PR-AUC/log loss/calibration, CTR/approval/issued@k, expected revenue@k,
no-offer rate, segment stability и rules baseline. Дополнительно обязательны delayed
label policy, partner-quality monitoring, bias/compliance review, rollback и ручное
promotion approval. Пока эти условия не выполнены, rules остаются production default.
