"use client";

import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Banknote,
  Braces,
  Calculator,
  CheckCircle2,
  CircleGauge,
  FileJson,
  Gauge,
  Landmark,
  LoaderCircle,
  LockKeyhole,
  ScanLine,
  ShieldCheck,
  UserRound,
  WalletCards,
} from "lucide-react";
import {
  apiFetch,
  type FeatureSchema,
  type ScoreResult,
  formatPercent,
} from "../lib/api";
import { calculateAnnuity, calculatePrincipal } from "../lib/credit-calculator.mjs";
import {
  buildPersonalFeatures,
  initialPersonalForm,
  numericValue,
  parsePersonalFormDraft,
  validatePersonalForm,
  type FeatureValue,
  type NumericField,
  type PersonalFormDraft,
} from "../lib/personal-score";
import { NumericInput } from "./NumericInput";

type WorkspaceMode = "personal" | "expert";

const initialPayload = `{
  "AMT_INCOME_TOTAL": 180000,
  "AMT_CREDIT": 450000,
  "AMT_ANNUITY": 24000,
  "AGE_YEARS": 36,
  "NAME_CONTRACT_TYPE": "Cash loans",
  "EXT_SOURCE_2": 0.61,
  "EXT_SOURCE_3": 0.48
}`;

const moneyFormatter = new Intl.NumberFormat("ru-RU", {
  style: "currency",
  currency: "RUB",
  maximumFractionDigits: 0,
});

function formatMoney(value: number): string {
  return moneyFormatter.format(Number.isFinite(value) ? Math.round(value) : 0);
}

function filterToSchema(
  features: Record<string, FeatureValue>,
  schema: FeatureSchema,
): Record<string, FeatureValue> {
  const knownFeatures = new Set([...schema.numeric_features, ...schema.categorical_features]);
  return Object.fromEntries(Object.entries(features).filter(([name]) => knownFeatures.has(name)));
}

export function ScoreWorkspace() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<WorkspaceMode>("personal");
  const [schema, setSchema] = useState<FeatureSchema | null>(null);
  const [schemaError, setSchemaError] = useState<string | null>(null);
  const [form, setForm] = useState<PersonalFormDraft>(initialPersonalForm);
  const [consent, setConsent] = useState(false);
  const [payload, setPayload] = useState(initialPayload);
  const [requestId, setRequestId] = useState("");
  const [result, setResult] = useState<ScoreResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    apiFetch<FeatureSchema>("feature_schema")
      .then((data) => {
        setSchema(data);
        setSchemaError(null);
      })
      .catch((reason: Error) => setSchemaError(reason.message));
  }, []);

  const scenario = useMemo(() => {
    const creditAmount = numericValue(form.creditAmount);
    const annualRate = numericValue(form.annualRate);
    const termMonths = numericValue(form.termMonths);
    const currentDebtPayment = numericValue(form.currentDebtPayment);
    const monthlyIncome = numericValue(form.monthlyIncome);
    const comfortableShare = numericValue(form.comfortableShare);
    const newPayment = calculateAnnuity(creditAmount, annualRate, termMonths);
    const totalPayments = newPayment + currentDebtPayment;
    const recommendedPayment = monthlyIncome * comfortableShare / 100;
    const availableForNewLoan = Math.max(0, recommendedPayment - currentDebtPayment);
    const maxPrincipal = calculatePrincipal(availableForNewLoan, annualRate, termMonths);
    const monthlyReserve = monthlyIncome - totalPayments;
    const paymentLoad = monthlyIncome > 0 ? totalPayments / monthlyIncome : 0;

    return {
      newPayment,
      totalPayments,
      recommendedPayment,
      maxPrincipal,
      monthlyReserve,
      paymentLoad,
      withinComfort: totalPayments <= recommendedPayment && monthlyReserve >= 0,
    };
  }, [form]);

  const updateNumber = (field: NumericField, rawValue: string) => {
    setForm((current) => ({ ...current, [field]: rawValue }));
    setResult(null);
    setError(null);
  };

  const updateChoice = <Key extends keyof PersonalFormDraft>(field: Key, value: PersonalFormDraft[Key]) => {
    setForm((current) => ({ ...current, [field]: value }));
    setResult(null);
    setError(null);
  };

  const switchMode = (nextMode: WorkspaceMode) => {
    setMode(nextMode);
    setResult(null);
    setError(null);
  };

  const loadJson = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      setPayload(await file.text());
      setError(null);
      setResult(null);
    } catch {
      setError("Не удалось прочитать JSON-файл.");
    }
  };

  const scoreFeatures = async (features: Record<string, FeatureValue>) => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const score = await apiFetch<ScoreResult>("score", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          request_id: requestId.trim() || undefined,
          features,
        }),
      });
      setResult(score);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const submitPersonal = async () => {
    const parsed = parsePersonalFormDraft(form);
    if (!parsed.form) {
      setError(parsed.error);
      return;
    }

    const validationError = validatePersonalForm(parsed.form);
    if (validationError) {
      setError(validationError);
      return;
    }
    if (!schema) {
      setError("Контракт модели недоступен. Финансовый расчёт работает, но ML-оценку сейчас запустить нельзя.");
      return;
    }
    if (!consent) {
      setError("Подтвердите отправку данных в сервис и запись результата в audit log.");
      return;
    }

    const newPayment = calculateAnnuity(
      parsed.form.creditAmount,
      parsed.form.annualRate,
      parsed.form.termMonths,
    );
    const features = filterToSchema(buildPersonalFeatures(parsed.form, newPayment), schema);
    await scoreFeatures(features);
  };

  const submitExpert = async () => {
    let features: Record<string, FeatureValue>;
    try {
      const parsed = JSON.parse(payload) as unknown;
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("Ожидается JSON-объект признаков.");
      }
      features = parsed as Record<string, FeatureValue>;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Некорректный JSON.");
      return;
    }
    await scoreFeatures(features);
  };

  return (
    <div className="page-stack">
      <section className="page-intro score-intro">
        <div>
          <span className="section-kicker">Финансовый сценарий · ML risk check</span>
          <h2>Оцените кредитную нагрузку до заявки.</h2>
          <p>
            Рассчитайте платёж и запас бюджета без отправки данных. При необходимости отдельно
            запустите предварительную оценку риска на портфельной ML-модели.
          </p>
        </div>
        <div className="schema-summary">
          <span>Модельный контракт</span>
          <strong>{schema?.feature_count ?? "—"} признаков</strong>
          <small>
            анкета передаёт только известные модели поля
          </small>
        </div>
      </section>

      <div className="score-mode-switch" role="tablist" aria-label="Режим оценки">
        <button
          type="button"
          role="tab"
          aria-selected={mode === "personal"}
          className={mode === "personal" ? "is-active" : ""}
          onClick={() => switchMode("personal")}
        >
          <Calculator size={17} /> Для себя
          <span>понятная анкета</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === "expert"}
          className={mode === "expert" ? "is-active" : ""}
          onClick={() => switchMode("expert")}
        >
          <Braces size={17} /> Экспертный JSON
          <span>готовые признаки</span>
        </button>
      </div>

      {mode === "personal" ? (
        <section className="score-layout personal-score-layout">
          <article className="score-form personal-form panel">
            <div className="panel-heading personal-section-heading">
              <div>
                <span className="form-step">01</span>
                <span className="section-kicker">Параметры кредита</span>
                <h3>Какой кредит вы рассматриваете?</h3>
              </div>
              <Landmark size={24} />
            </div>

            <div className="personal-fields three-columns">
              <label className="field-label" htmlFor="credit-amount">
                Сумма кредита, ₽
                <NumericInput id="credit-amount" min="10000" max="100000000" step="10000" value={form.creditAmount} onValueChange={(value) => updateNumber("creditAmount", value)} />
              </label>
              <label className="field-label" htmlFor="term-months">
                Срок, месяцев
                <NumericInput id="term-months" min="3" max="360" step="1" value={form.termMonths} onValueChange={(value) => updateNumber("termMonths", value)} />
              </label>
              <label className="field-label" htmlFor="annual-rate">
                Ставка, % годовых
                <NumericInput id="annual-rate" min="0" max="100" step="0.1" value={form.annualRate} onValueChange={(value) => updateNumber("annualRate", value)} />
              </label>
            </div>

            <div className="inline-calculation">
              <Calculator size={19} />
              <div><span>Расчётный платёж</span><strong>{formatMoney(scenario.newPayment)} / мес.</strong></div>
              <small>аннуитетный расчёт, без комиссий и страховок</small>
            </div>

            <div className="form-divider" />

            <div className="panel-heading personal-section-heading">
              <div>
                <span className="form-step">02</span>
                <span className="section-kicker">Доход и обязательства</span>
                <h3>Сколько остаётся после платежей?</h3>
              </div>
              <WalletCards size={24} />
            </div>

            <div className="personal-fields two-columns">
              <label className="field-label" htmlFor="monthly-income">
                Доход в месяц, ₽
                <NumericInput id="monthly-income" min="10000" max="100000000" step="5000" value={form.monthlyIncome} onValueChange={(value) => updateNumber("monthlyIncome", value)} />
              </label>
              <label className="field-label" htmlFor="current-debt">
                Другие кредитные платежи, ₽ / мес.
                <NumericInput id="current-debt" min="0" max="100000000" step="1000" value={form.currentDebtPayment} onValueChange={(value) => updateNumber("currentDebtPayment", value)} />
              </label>
            </div>

            <label className="range-field" htmlFor="comfortable-share">
              <span><strong>Комфортная доля платежей</strong><b>{form.comfortableShare}% дохода</b></span>
              <input id="comfortable-share" type="range" min="25" max="45" step="1" value={form.comfortableShare} onChange={(event) => updateNumber("comfortableShare", event.target.value)} />
              <small>Это изменяемый ориентир для планирования бюджета, а не правило банка.</small>
            </label>

            <div className="form-divider" />

            <div className="panel-heading personal-section-heading">
              <div>
                <span className="form-step">03</span>
                <span className="section-kicker">Коротко о вас</span>
                <h3>Данные для модельной оценки</h3>
              </div>
              <UserRound size={24} />
            </div>

            <div className="personal-fields three-columns">
              <label className="field-label" htmlFor="age">
                Возраст
                <NumericInput id="age" min="18" max="75" step="1" value={form.age} onValueChange={(value) => updateNumber("age", value)} />
              </label>
              <label className="field-label" htmlFor="employment-years">
                Стаж, лет
                <NumericInput id="employment-years" min="0" max="60" step="0.5" value={form.employmentYears} onValueChange={(value) => updateNumber("employmentYears", value)} />
              </label>
              <label className="field-label" htmlFor="family-members">
                Членов семьи
                <NumericInput id="family-members" min="1" max="20" step="1" value={form.familyMembers} onValueChange={(value) => updateNumber("familyMembers", value)} />
              </label>
              <label className="field-label" htmlFor="children">
                Детей
                <NumericInput id="children" min="0" max="20" step="1" value={form.children} onValueChange={(value) => updateNumber("children", value)} />
              </label>
              <label className="field-label" htmlFor="income-type">
                Тип занятости
                <select id="income-type" value={form.incomeType} onChange={(event) => updateChoice("incomeType", event.target.value)}>
                  <option value="Working">Работа по найму</option>
                  <option value="Commercial associate">Предпринимательство</option>
                  <option value="State servant">Госслужба</option>
                  <option value="Pensioner">Пенсия</option>
                  <option value="Student">Студент</option>
                  <option value="Unemployed">Без работы</option>
                </select>
              </label>
              <label className="field-label" htmlFor="housing-type">
                Жильё
                <select id="housing-type" value={form.housingType} onChange={(event) => updateChoice("housingType", event.target.value)}>
                  <option value="House / apartment">Своё или семейное</option>
                  <option value="Rented apartment">Аренда</option>
                  <option value="With parents">С родителями</option>
                  <option value="Municipal apartment">Муниципальное</option>
                  <option value="Office apartment">Служебное</option>
                </select>
              </label>
            </div>

            <div className="choice-row">
              <button type="button" className={form.ownsRealty ? "is-selected" : ""} aria-pressed={form.ownsRealty} onClick={() => updateChoice("ownsRealty", !form.ownsRealty)}>
                <CheckCircle2 size={16} /> Есть недвижимость
              </button>
              <button type="button" className={form.ownsCar ? "is-selected" : ""} aria-pressed={form.ownsCar} onClick={() => updateChoice("ownsCar", !form.ownsCar)}>
                <CheckCircle2 size={16} /> Есть автомобиль
              </button>
            </div>

            <label className="consent-row" htmlFor="score-consent">
              <input id="score-consent" type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} />
              <span>
                Я понимаю, что при запуске ML-оценки введённые данные будут отправлены в сервис,
                а запрос и результат сохранены в audit log.
              </span>
            </label>

            {schemaError ? (
              <div className="form-error" role="alert"><AlertTriangle size={18} /> {schemaError}</div>
            ) : null}
            {error ? (
              <div className="form-error" role="alert"><AlertTriangle size={18} /> {error}</div>
            ) : null}

            <button className="button button-dark button-full" type="button" onClick={submitPersonal} disabled={loading || !schema}>
              {loading ? <LoaderCircle className="spin" size={18} /> : <ScanLine size={18} />}
              {loading ? "Оцениваем…" : "Получить предварительную ML-оценку"}
              {!loading ? <ArrowRight size={18} /> : null}
            </button>
            <p className="model-disclaimer">
              Демо-оценка не является офертой, кредитным решением или финансовой рекомендацией.
            </p>
          </article>

          <PersonalResult scenario={scenario} result={result} />
        </section>
      ) : (
        <section className="score-layout">
          <article className="score-form panel">
            <div className="panel-heading">
              <div>
                <span className="section-kicker">Feature payload</span>
                <h3>Подготовленные признаки</h3>
              </div>
              <button className="button button-mini" type="button" onClick={() => fileRef.current?.click()}>
                <FileJson size={16} /> Из JSON
              </button>
              <input ref={fileRef} type="file" accept="application/json,.json" onChange={loadJson} hidden />
            </div>

            <label className="field-label" htmlFor="request-id">
              Request ID <span className="optional">необязательно</span>
              <input id="request-id" value={requestId} onChange={(event) => setRequestId(event.target.value)} placeholder="например, application-2026-0042" maxLength={128} spellCheck={false} />
            </label>

            <label className="field-label" htmlFor="feature-json">
              JSON с признаками
              <textarea id="feature-json" className="json-editor" value={payload} onChange={(event) => setPayload(event.target.value)} spellCheck={false} rows={13} />
            </label>

            <div className="editor-note">
              <Braces size={17} />
              <span>
                Режим предназначен для подготовленного feature payload. Используйте контракт
                текущего model bundle или выгрузку build-full-features.
              </span>
            </div>

            {error ? <div className="form-error" role="alert"><AlertTriangle size={18} /> {error}</div> : null}

            <button className="button button-dark button-full" type="button" onClick={submitExpert} disabled={loading}>
              {loading ? <LoaderCircle className="spin" size={18} /> : <ScanLine size={18} />}
              {loading ? "Рассчитываем…" : "Рассчитать риск"}
              {!loading ? <ArrowRight size={18} /> : null}
            </button>
          </article>

          <ModelResult result={result} expert />
        </section>
      )}
    </div>
  );
}

interface Scenario {
  newPayment: number;
  totalPayments: number;
  recommendedPayment: number;
  maxPrincipal: number;
  monthlyReserve: number;
  paymentLoad: number;
  withinComfort: boolean;
}

function PersonalResult({ scenario, result }: { scenario: Scenario; result: ScoreResult | null }) {
  return (
    <aside className="personal-summary">
      <div className="summary-topline">
        <span className={`scenario-status ${scenario.withinComfort ? "comfortable" : "overloaded"}`}>
          {scenario.withinComfort ? <CheckCircle2 size={17} /> : <AlertTriangle size={17} />}
          {scenario.withinComfort ? "В пределах ориентира" : "Нагрузка выше ориентира"}
        </span>
        <span>расчёт обновляется сразу</span>
      </div>

      <div className="payment-hero">
        <span>Новый платёж</span>
        <strong>{formatMoney(scenario.newPayment)}</strong>
        <small>в месяц</small>
      </div>

      <div className="scenario-grid">
        <div><Banknote size={18} /><span>Комфортная сумма кредита</span><strong>{formatMoney(scenario.maxPrincipal)}</strong></div>
        <div><WalletCards size={18} /><span>Останется после платежей</span><strong className={scenario.monthlyReserve < 0 ? "is-negative" : ""}>{formatMoney(scenario.monthlyReserve)}</strong></div>
        <div><Gauge size={18} /><span>Общая платёжная нагрузка</span><strong>{formatPercent(scenario.paymentLoad, 0)}</strong></div>
        <div><Calculator size={18} /><span>Ориентир всех платежей</span><strong>{formatMoney(scenario.recommendedPayment)}</strong></div>
      </div>

      <div className="summary-note">
        <CircleGauge size={19} />
        <p>
          «Комфортная сумма» рассчитана по выбранной доле дохода, ставке и сроку. Комиссии,
          страховки, расходы семьи и требования конкретного банка не учтены.
        </p>
      </div>

      <div className="model-result-section">
        <div className="model-result-title">
          <div><span className="section-kicker light">ML-модель</span><h3>Предварительный риск</h3></div>
          <ShieldCheck size={23} />
        </div>
        {result ? <ModelResultContent result={result} /> : (
          <div className="model-empty">
            <LockKeyhole size={24} />
            <div>
              <strong>Запускается отдельно</strong>
              <span>Заполните анкету, подтвердите отправку данных и запросите оценку.</span>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}

function ModelResult({ result, expert = false }: { result: ScoreResult | null; expert?: boolean }) {
  return (
    <aside className={`score-result ${result ? "has-result" : ""}`}>
      {result ? <ModelResultContent result={result} expert={expert} /> : (
        <div className="result-placeholder">
          <div className="placeholder-symbol"><CircleGauge size={35} /></div>
          <span className="section-kicker">Результат</span>
          <h3>Здесь появится оценка</h3>
          <p>Вероятность дефолта, риск-группа, качество входа и локальные факторы будут показаны после проверки payload.</p>
          <div className="placeholder-contract"><ShieldCheck size={18} /><span>Ответ будет записан в PostgreSQL audit log</span></div>
        </div>
      )}
    </aside>
  );
}

function ModelResultContent({ result, expert = false }: { result: ScoreResult; expert?: boolean }) {
  return (
    <>
      <div className="result-header">
        <span className={`result-decision ${result.decision}`}>
          {result.decision === "approve" ? <CheckCircle2 size={17} /> : <AlertTriangle size={17} />}
          {expert
            ? (result.decision === "approve" ? "Одобрить" : "Отказать")
            : (result.decision === "approve" ? "Риск ниже порога" : "Повышенный риск")}
        </span>
        <span className="mono result-id">{result.request_id}</span>
      </div>

      <div className={`probability-ring ${result.decision}`} style={{ "--probability": `${Math.round(result.default_probability * 100)}%` } as CSSProperties}>
        <div><strong>{formatPercent(result.default_probability, 2)}</strong><span>оценка вероятности дефолта</span></div>
      </div>

      <div className="result-facts">
        <div><span>Риск-группа</span><strong>{result.risk_band}</strong></div>
        <div><span>Порог модели</span><strong>{formatPercent(result.decision_threshold, 0)}</strong></div>
        <div><span>Покрытие входа</span><strong>{formatPercent(result.input_quality.supplied_feature_coverage, 0)}</strong></div>
      </div>

      <div className="quality-block">
        <div className="quality-head"><span>Полнота относительно feature-контракта</span><strong>{formatPercent(result.input_quality.supplied_feature_coverage, 0)}</strong></div>
        <div className="quality-track"><i style={{ width: `${result.input_quality.supplied_feature_coverage * 100}%` }} /></div>
        <small>{result.missing_feature_count} признаков не передано · latency {result.latency_ms.toFixed(0)} ms</small>
      </div>

      <div className="reasons-block">
        <span className="section-kicker">Локальные факторы повышенного риска</span>
        {result.reason_codes.length ? result.reason_codes.slice(0, 4).map((reason) => (
          <div className="reason-row" key={`${reason.code}-${reason.contribution}`}>
            <Gauge size={17} />
            <div><strong>{reason.feature}</strong><span>{reason.description}</span></div>
          </div>
        )) : <p className="muted">Положительные reason codes не найдены.</p>}
      </div>
    </>
  );
}
