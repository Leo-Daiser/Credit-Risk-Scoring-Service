"use client";

import {
  AlertTriangle,
  ArrowRight,
  Building2,
  BookOpenCheck,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleGauge,
  LoaderCircle,
  Pencil,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Star,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { CreditProfileInput, ImprovementScenario, OfferMatchResult, RankedOffer } from "../lib/api";
import { consumeTransientAssessmentContext } from "../lib/assessment-context";
import { apiFetch, formatPercent } from "../lib/api";
import { createAnonymousSessionId, recordPublicEvent } from "../lib/public-analytics";
import { NumericInput } from "./NumericInput";
import { PUBLIC_PROFILE_LIMITS } from "../lib/public-profile-constraints";

const initialProfile: CreditProfileInput = {
  age_band: "18_21",
  income_band: "unknown",
  employment_type: "unknown",
  requested_amount_band: "lt_100k",
  term_months: PUBLIC_PROFILE_LIMITS.termMinMonths,
  existing_monthly_payments_band: "unknown",
  credit_history_band: "unknown",
  loan_purpose: "cash",
  consent_to_process: false,
  consent_to_ad_personalization: false,
};

const confidenceLabels: Record<string, string> = {
  low: "низкая", basic: "базовая", medium: "средняя", high: "высокая",
};
const bandLabels: Record<string, string> = {
  low: "низкая", moderate: "умеренная", high: "повышенная", very_high: "высокая",
  unknown: "не определена", comfortable: "комфортная", manageable: "умеренная",
  stretched: "повышенная", unaffordable: "очень высокая",
};
const productLabels: Record<string, string> = {
  cash: "Кредит наличными", refinance: "Рефинансирование", car: "Автокредит",
  repair: "Кредит на ремонт", education: "Кредит на образование", medical: "Кредит на лечение",
};
const money = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });

function amountBandFor(value: number): CreditProfileInput["requested_amount_band"] {
  if (value < 100_000) return "lt_100k";
  if (value <= 300_000) return "100k_300k";
  if (value <= 700_000) return "300k_700k";
  if (value <= 1_500_000) return "700k_1_5m";
  return "gt_1_5m";
}

function paymentsBandFor(value: number): CreditProfileInput["existing_monthly_payments_band"] {
  if (value === 0) return "zero";
  if (value < 10_000) return "lt_10k";
  if (value <= 30_000) return "10k_30k";
  if (value <= 60_000) return "30k_60k";
  return "gt_60k";
}

function ageBandFor(value: number): CreditProfileInput["age_band"] {
  if (value <= 21) return "18_21";
  if (value <= 30) return "22_30";
  if (value <= 45) return "31_45";
  if (value <= 60) return "46_60";
  return "60_plus";
}

function incomeBandFor(value: number): CreditProfileInput["income_band"] {
  if (value < 50_000) return "lt_50k";
  if (value <= 100_000) return "50k_100k";
  if (value <= 150_000) return "100k_150k";
  if (value <= 250_000) return "150k_250k";
  return "gt_250k";
}

function amountForBand(value: CreditProfileInput["requested_amount_band"]): number {
  return { lt_100k: 75_000, "100k_300k": 200_000, "300k_700k": 500_000, "700k_1_5m": 1_000_000, gt_1_5m: 2_000_000 }[value];
}

export function OfferWorkspace({ showModelStatus = false }: { showModelStatus?: boolean }) {
  const [sessionId] = useState(createAnonymousSessionId);
  const [initialContext] = useState(consumeTransientAssessmentContext);
  const [profile, setProfile] = useState<CreditProfileInput>(() => initialContext ? {
    ...initialProfile,
    requested_amount: initialContext.amount,
    requested_amount_band: amountBandFor(initialContext.amount),
    term_months: initialContext.term,
    monthly_income: initialContext.monthlyIncome,
    income_band: incomeBandFor(initialContext.monthlyIncome),
    existing_monthly_payments: initialContext.existingPayments,
    existing_monthly_payments_band: paymentsBandFor(initialContext.existingPayments),
  } : initialProfile);
  const [termDraft, setTermDraft] = useState(() => initialContext ? String(initialContext.term) : "");
  const [amountDraft, setAmountDraft] = useState(() => initialContext ? String(initialContext.amount) : "");
  const [paymentsDraft, setPaymentsDraft] = useState(() => initialContext && initialContext.existingPayments > 0 ? String(initialContext.existingPayments) : "");
  const [hasPayments, setHasPayments] = useState<boolean | null>(() => initialContext ? initialContext.existingPayments > 0 : null);
  const [purposeDraft, setPurposeDraft] = useState<CreditProfileInput["loan_purpose"] | "">("");
  const [ageDraft, setAgeDraft] = useState("");
  const [incomeDraft, setIncomeDraft] = useState(() => initialContext ? String(initialContext.monthlyIncome) : "");
  const [employmentDraft, setEmploymentDraft] = useState("");
  const [step, setStep] = useState(1);
  const [result, setResult] = useState<OfferMatchResult | null>(null);
  const [previousResult, setPreviousResult] = useState<OfferMatchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [clicking, setClicking] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [transition, setTransition] = useState<{ url: string; partner: string; offer: string } | null>(null);
  const [showRecovery, setShowRecovery] = useState(false);
  const [recoveryDismissed, setRecoveryDismissed] = useState(false);
  const assessmentStarted = useRef(false);
  const viewedResultIds = useRef(new Set<string>());
  const transitionPrimaryRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (assessmentStarted.current) return;
    assessmentStarted.current = true;
    void recordPublicEvent("assessment_started", "assessment", sessionId).catch(() => undefined);
  }, [sessionId]);

  useEffect(() => {
    if (!result?.offers.length || recoveryDismissed) return;
    const onVisibility = () => {
      if (document.visibilityState === "visible") setShowRecovery(true);
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [result, recoveryDismissed]);

  useEffect(() => {
    if (!result) return;
    const resultId = result.profile_result.anonymous_profile_id;
    if (viewedResultIds.current.has(resultId)) return;
    viewedResultIds.current.add(resultId);
    window.scrollTo({ top: 0 });
    const metadata = {
      profile_band: result.profile_result.profile_band,
      pti_band: result.profile_result.pti_band,
    };
    const events: Array<Promise<void>> = [
      recordPublicEvent("profile_result_viewed", "result", sessionId, metadata),
      recordPublicEvent("offers_viewed", "result", sessionId, metadata),
    ];
    if (result.improvement_scenarios.length) {
      events.push(recordPublicEvent("improvement_viewed", "result", sessionId, metadata));
    }
    if (result.offers.length) {
      events.push(recordPublicEvent("recommended_offer_viewed", "result", sessionId, {
        ...metadata,
        offer_position: "recommended",
      }));
    } else {
      events.push(recordPublicEvent("no_eligible_offers_viewed", "result", sessionId, metadata));
    }
    void Promise.allSettled(events);
  }, [result, sessionId]);

  useEffect(() => {
    if (!transition) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setTransition(null);
    };
    document.addEventListener("keydown", closeOnEscape);
    transitionPrimaryRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
      previouslyFocused?.focus();
    };
  }, [transition]);

  const update = <K extends keyof CreditProfileInput>(key: K, value: CreditProfileInput[K]) => {
    setProfile((current) => ({ ...current, [key]: value }));
  };

  const stepError = (targetStep: number): string | null => {
    const amount = Number(amountDraft);
    const term = Number(termDraft);
    const age = Number(ageDraft);
    const income = Number(incomeDraft);
    const employmentYears = Number(employmentDraft);
    const payments = Number(paymentsDraft);
    if (targetStep === 1 && (!Number.isFinite(amount) || amount < PUBLIC_PROFILE_LIMITS.amountMin || amount > PUBLIC_PROFILE_LIMITS.amountMax)) return "Укажите примерную сумму от 1 до 10 000 000 ₽.";
    if (targetStep === 1 && (!Number.isInteger(term) || term < PUBLIC_PROFILE_LIMITS.termMinMonths || term > PUBLIC_PROFILE_LIMITS.termMaxMonths)) return "Укажите срок от 3 до 120 месяцев.";
    if (targetStep === 1 && purposeDraft === "") return "Выберите цель кредита.";
    if (targetStep === 2 && (!Number.isInteger(age) || age < PUBLIC_PROFILE_LIMITS.ageMin || age > PUBLIC_PROFILE_LIMITS.ageMax)) return "Укажите возраст от 18 до 75 лет.";
    if (targetStep === 2 && (!Number.isFinite(income) || income <= 0 || income > PUBLIC_PROFILE_LIMITS.monthlyIncomeMax)) return "Укажите примерный регулярный доход до 10 000 000 ₽.";
    if (targetStep === 2 && profile.employment_type === "unknown") return "Выберите тип занятости.";
    if (targetStep === 2 && (!Number.isFinite(employmentYears) || employmentYears < PUBLIC_PROFILE_LIMITS.employmentYearsMin || employmentYears > PUBLIC_PROFILE_LIMITS.employmentYearsMax)) return "Укажите стаж от 0 до 60 лет.";
    if (targetStep === 3 && hasPayments === null) return "Укажите, есть ли действующие кредитные платежи.";
    if (targetStep === 3 && hasPayments && (!Number.isFinite(payments) || payments <= 0 || payments > PUBLIC_PROFILE_LIMITS.existingPaymentsMax)) return "Укажите сумму текущих платежей больше нуля и не более 2 000 000 ₽.";
    return null;
  };

  const nextStep = () => {
    const message = stepError(step);
    if (message) {
      setError(message);
      return;
    }
    void recordPublicEvent("assessment_step_completed", "assessment", sessionId, { assessment_step: step as 1 | 2 | 3 | 4 }).catch(() => undefined);
    setError(null);
    setStep((current) => Math.min(current + 1, 4));
  };

  const submit = async () => {
    const term = Number(termDraft);
    const amount = amountDraft === "" ? undefined : Number(amountDraft);
    const payments = hasPayments ? Number(paymentsDraft) : 0;
    const age = ageDraft === "" ? undefined : Number(ageDraft);
    const monthlyIncome = incomeDraft === "" ? undefined : Number(incomeDraft);
    const employmentYears = employmentDraft === "" ? undefined : Number(employmentDraft);
    if (!Number.isInteger(term) || term < PUBLIC_PROFILE_LIMITS.termMinMonths || term > PUBLIC_PROFILE_LIMITS.termMaxMonths) {
      setError("Срок должен быть целым числом от 3 до 120 месяцев.");
      return;
    }
    if (amount === undefined || !Number.isFinite(amount) || amount <= 0 || amount > PUBLIC_PROFILE_LIMITS.amountMax) {
      setError("Точная сумма должна быть от 1 до 10 000 000 ₽ или оставлена пустой.");
      return;
    }
    if (hasPayments === null || !Number.isFinite(payments) || payments < 0 || payments > PUBLIC_PROFILE_LIMITS.existingPaymentsMax) {
      setError("Текущие платежи должны быть от 0 до 2 000 000 ₽.");
      return;
    }
    if (age === undefined || !Number.isInteger(age) || age < PUBLIC_PROFILE_LIMITS.ageMin || age > PUBLIC_PROFILE_LIMITS.ageMax) {
      setError("Возраст должен быть целым числом от 18 до 75 лет.");
      return;
    }
    if (monthlyIncome === undefined || !Number.isFinite(monthlyIncome) || monthlyIncome <= 0 || monthlyIncome > PUBLIC_PROFILE_LIMITS.monthlyIncomeMax) {
      setError("Доход должен быть положительным числом до 10 000 000 ₽.");
      return;
    }
    if (employmentYears === undefined || !Number.isFinite(employmentYears) || employmentYears < PUBLIC_PROFILE_LIMITS.employmentYearsMin || employmentYears > PUBLIC_PROFILE_LIMITS.employmentYearsMax) {
      setError("Стаж должен быть от 0 до 60 лет.");
      return;
    }
    if (!profile.consent_to_process) {
      setError("Для подбора необходимо согласие на обработку введённых диапазонов.");
      return;
    }
    if (purposeDraft === "" || profile.employment_type === "unknown") {
      setError("Заполните цель кредита и тип занятости.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const submittedProfile: CreditProfileInput = {
        ...profile,
        term_months: term,
        requested_amount: amount,
        requested_amount_band: amountBandFor(amount),
        existing_monthly_payments: payments,
        existing_monthly_payments_band: paymentsBandFor(payments),
        age,
        age_band: ageBandFor(age),
        monthly_income: monthlyIncome,
        income_band: incomeBandFor(monthlyIncome),
        employment_years: employmentYears,
        loan_purpose: purposeDraft,
      };
      void recordPublicEvent("assessment_completed", "assessment", sessionId).catch(() => undefined);
      const response = await requestMatch(submittedProfile, "public_assessment");
      setProfile(submittedProfile);
      setResult(response);
      setPreviousResult(null);
    } catch {
      setError("Не удалось выполнить оценку. Попробуйте ещё раз.");
    } finally {
      setLoading(false);
    }
  };

  const requestMatch = (nextProfile: CreditProfileInput, source: string) => apiFetch<OfferMatchResult>("v1/offers/match", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Anonymous-Session-ID": sessionId },
    body: JSON.stringify({
      profile: nextProfile,
      context: { anonymous_session_id: sessionId, source },
      limit: 5,
    }),
  });

  const applyScenario = async (amount: number, term: number, payments: number, scenarioType: ImprovementScenario["factor"]) => {
    setLoading(true);
    setError(null);
    const nextProfile: CreditProfileInput = {
      ...profile,
      requested_amount: amount,
      requested_amount_band: amountBandFor(amount),
      term_months: term,
      existing_monthly_payments: payments,
      existing_monthly_payments_band: paymentsBandFor(payments),
    };
    try {
      void recordPublicEvent("scenario_applied", "scenario", sessionId, {
        scenario_type: scenarioType,
        profile_band: result?.profile_result.profile_band,
        pti_band: result?.profile_result.pti_band,
      }).catch(() => undefined);
      const baseline = result;
      const response = await requestMatch(nextProfile, "public_scenario");
      setPreviousResult(baseline);
      setProfile(nextProfile);
      setAmountDraft(String(Math.round(amount)));
      setTermDraft(String(term));
      setPaymentsDraft(String(Math.round(payments)));
      setResult(response);
      document.getElementById("riskline-profile")?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch {
      setError("Не удалось проверить сценарий. Попробуйте ещё раз.");
    } finally {
      setLoading(false);
    }
  };

  const openOffer = async (offer: RankedOffer) => {
    if (!result) return;
    setClicking(offer.offer_id);
    setError(null);
    try {
      const click = await apiFetch<{ click_id: string; redirect_url: string }>(
        `v1/offers/${offer.offer_id}/click`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Anonymous-Session-ID": sessionId },
          body: JSON.stringify({
            profile_id: result.profile_result.anonymous_profile_id,
            anonymous_session_id: sessionId,
            idempotency_key: `${result.profile_result.anonymous_profile_id}-${offer.offer_id}`,
          }),
        },
      );
      setTransition({
        url: click.redirect_url,
        partner: offer.advertiser_name,
        offer: offer.product_name,
      });
      void recordPublicEvent("partner_transition_viewed", "result", sessionId, {
        offer_position: offer.rank === 1 ? "recommended" : "alternative",
      }).catch(() => undefined);
      setClicking(null);
    } catch {
      setError("Не удалось подготовить переход. Попробуйте ещё раз.");
      setClicking(null);
    }
  };

  return (
    <div className="offers-page">
      {!result ? (
        <>
          <section className="assessment-intro">
            <span className="section-kicker">Оценка финансового профиля</span>
            <h1>Получите персональную оценку Riskline</h1>
            <p>Четыре коротких шага. Можно указывать примерные значения — паспорт, телефон, документы и данные БКИ не нужны.</p>
            <div className="privacy-chip"><ShieldCheck size={20} /> Введённые точные значения не сохраняются в браузере</div>
          </section>

          <section className="assessment-wizard" aria-labelledby="assessment-step-title">
            <div className="assessment-progress">
              <div><span>Шаг {step} из 4</span><strong>{["Что вы хотите получить", "Доход и работа", "Текущая нагрузка", "Проверка данных"][step - 1]}</strong></div>
              <div className="assessment-progress-track" aria-hidden="true"><i style={{ width: `${step * 25}%` }} /></div>
            </div>

            {loading ? <AssessmentLoading /> : (
              <div className="assessment-step-body">
                {step === 1 ? (
                  <fieldset className="assessment-fieldset">
                    <legend id="assessment-step-title">Что вы хотите получить?</legend>
                    <p>Эти параметры нужны для расчёта платежа и проверки лимитов предложений.</p>
                    <div className="assessment-fields">
                      <NumberField id="assessment-amount" label="Желаемая сумма, ₽" help="Можно указать примерно." value={amountDraft} onChange={setAmountDraft} min={1} />
                      <NumberField id="assessment-term" label="Срок, месяцев" help="От 3 до 120 месяцев." value={termDraft} onChange={setTermDraft} min={3} max={120} step={1} />
                      <SelectField id="assessment-purpose" label="Цель кредита" help="Нужна для подбора подходящего типа продукта." value={purposeDraft} onChange={(value) => setPurposeDraft(value as CreditProfileInput["loan_purpose"] | "")} options={[["", "Выберите цель"], ["cash", "Наличные"], ["refinance", "Рефинансирование"], ["car", "Автомобиль"], ["repair", "Ремонт"], ["education", "Образование"], ["medical", "Лечение"], ["other", "Другое"]]} />
                    </div>
                  </fieldset>
                ) : null}
                {step === 2 ? (
                  <fieldset className="assessment-fieldset">
                    <legend id="assessment-step-title">Ваш доход и работа</legend>
                    <p>Доход и стаж помогают оценить текущий сценарий. Указывать работодателя не нужно.</p>
                    <div className="assessment-fields">
                      <NumberField id="assessment-age" label="Возраст, лет" help="Нужен для базовых ограничений продуктов." value={ageDraft} onChange={setAgeDraft} min={18} max={75} step={1} />
                      <NumberField id="assessment-income" label="Ваш регулярный доход в месяц, ₽" help="Укажите приблизительный регулярный доход, который можно подтвердить при необходимости. Это не доход всей семьи." value={incomeDraft} onChange={setIncomeDraft} min={1} />
                      <SelectField id="assessment-employment" label="Занятость" help="Используется в модельной оценке и правилах отдельных предложений." value={profile.employment_type} onChange={(value) => update("employment_type", value as CreditProfileInput["employment_type"])} options={[["unknown", "Выберите занятость"], ["employee", "Работаю по найму"], ["self_employed", "Самозанятый"], ["individual_entrepreneur", "ИП"], ["pensioner", "Пенсионер"], ["unofficial", "Неофициальная занятость"], ["unemployed", "Сейчас не работаю"]]} />
                      <NumberField id="assessment-employment-years" label="Подтверждаемый стаж, лет" help="Стаж в текущем виде занятости; можно округлить до половины года." value={employmentDraft} onChange={setEmploymentDraft} min={0} max={60} step={0.5} />
                    </div>
                  </fieldset>
                ) : null}
                {step === 3 ? (
                  <fieldset className="assessment-fieldset">
                    <legend id="assessment-step-title">Текущая финансовая нагрузка</legend>
                    <p>Эти данные нужны только для расчёта долговой нагрузки. Riskline не проверяет их через БКИ.</p>
                    <div className="assessment-fields">
                      <fieldset className="payment-choice"><legend>Есть действующие кредитные платежи?</legend><div role="group" aria-label="Наличие действующих кредитных платежей"><button type="button" className={hasPayments === false ? "is-selected" : ""} aria-pressed={hasPayments === false} onClick={() => { setHasPayments(false); setPaymentsDraft(""); update("existing_monthly_payments_band", "zero"); }}>Нет</button><button type="button" className={hasPayments === true ? "is-selected" : ""} aria-pressed={hasPayments === true} onClick={() => { setHasPayments(true); update("existing_monthly_payments_band", "unknown"); }}>Да</button></div><small>Учитываются платежи по действующим кредитам и картам.</small></fieldset>
                      {hasPayments ? <NumberField id="assessment-payments" label="Сумма текущих платежей в месяц, ₽" help="Укажите приблизительную общую сумму обязательных кредитных платежей." value={paymentsDraft} onChange={setPaymentsDraft} min={1} /> : null}
                      <SelectField id="assessment-history" label="Кредитная история — по вашей оценке" help="Riskline не запрашивает и не проверяет данные БКИ." value={profile.credit_history_band} onChange={(value) => update("credit_history_band", value as CreditProfileInput["credit_history_band"])} options={[["unknown", "Не знаю"], ["good", "Просрочек не помню"], ["minor_overdues", "Были редкие короткие просрочки"], ["serious_overdues", "Были существенные просрочки"], ["no_history", "Кредитной истории почти нет"], ["average", "Ситуация неоднозначная"]]} />
                    </div>
                  </fieldset>
                ) : null}
                {step === 4 ? (
                  <fieldset className="assessment-fieldset assessment-review">
                    <legend id="assessment-step-title">Проверьте данные</legend>
                    <p>Riskline рассчитает долговую нагрузку, выполнит оценку профиля и проверит совместимость предложений.</p>
                    <dl className="assessment-review-grid">
                      <div><dt>Сумма и срок</dt><dd>{money.format(Number(amountDraft) || 0)} ₽ · {termDraft} мес.</dd></div>
                      <div><dt>Возраст и доход</dt><dd>{ageDraft} лет · {money.format(Number(incomeDraft) || 0)} ₽/мес.</dd></div>
                      <div><dt>Занятость и стаж</dt><dd>{employmentLabel(profile.employment_type)} · {employmentDraft} лет</dd></div>
                      <div><dt>Текущие кредитные платежи</dt><dd>{hasPayments ? `${money.format(Number(paymentsDraft) || 0)} ₽/мес.` : "Нет"}</dd></div>
                    </dl>
                    <label className="consent-row" htmlFor="assessment-consent"><input id="assessment-consent" type="checkbox" checked={profile.consent_to_process} onChange={(event) => update("consent_to_process", event.target.checked)} /><span>Согласен на обработку указанных данных для предварительной оценки и подбора. Это не кредитное решение.</span></label>
                    <label className="consent-row secondary-consent" htmlFor="assessment-ad-consent"><input id="assessment-ad-consent" type="checkbox" checked={profile.consent_to_ad_personalization} onChange={(event) => update("consent_to_ad_personalization", event.target.checked)} /><span>Разрешаю персонализацию рекламных предложений.</span></label>
                  </fieldset>
                ) : null}

                {error ? <div className="form-error" role="alert" id="assessment-error"><AlertTriangle size={18} />{error}</div> : null}
                <div className="assessment-actions">
                  {step > 1 ? <button className="button button-ghost" type="button" onClick={() => { setError(null); setStep(step - 1); }}><ChevronLeft size={17} /> Назад</button> : <span />}
                  {step < 4 ? <button className="button button-dark" type="button" onClick={nextStep}>Продолжить <ChevronRight size={17} /></button> : <button className="button button-dark" type="button" onClick={submit}><CircleGauge size={18} /> Получить оценку</button>}
                </div>
              </div>
            )}
          </section>
          <WhatYouGet />
        </>
      ) : (
        <main className="assessment-report" aria-live="polite">
          <div className="assessment-report-toolbar">
            <div><span className="section-kicker">Персональный результат</span><h1>Ваша оценка Riskline</h1></div>
            <button className="button button-ghost" type="button" onClick={() => { setResult(null); setPreviousResult(null); setStep(4); window.scrollTo({ top: 0, behavior: "smooth" }); }}><Pencil size={16} /> Изменить данные</button>
          </div>
          {showModelStatus && !result.profile_result.model_available ? <div className="dev-model-warning" role="status"><AlertTriangle size={18} /><div><strong>Публичная ML-модель не загружена</strong><span>Локальный demo использует прозрачный rules fallback. Запустите prepare-local-ml.</span></div></div> : null}
          {showRecovery ? <div className="exit-recovery" role="status"><div><strong>Сравните предложения перед выходом</strong><span>Результат останется на странице, пока вкладка открыта.</span></div><button type="button" aria-label="Закрыть подсказку" onClick={() => { setShowRecovery(false); setRecoveryDismissed(true); }}><X size={16} /></button></div> : null}
          <ProfileSummary result={result} profile={profile} />
          <ProfileFactors result={result} />
          <ImprovementPanel result={result} scenarios={result.improvement_scenarios} onApply={applyScenario} loading={loading} />
          <ScenarioSimulator profile={profile} result={result} previousResult={previousResult} onApply={applyScenario} loading={loading} sessionId={sessionId} />
          <CreditHistoryAdvice band={profile.credit_history_band} />
          {profile.existing_monthly_payments_band !== "zero" ? <div className="refinance-trigger"><strong>Проверить рефинансирование</strong><span>Сравните условия рефинансирования с действующими обязательствами. Без остатка долга, ставки и срока Riskline не рассчитывает экономию и не обещает снижение платежа.</span></div> : null}
          <section className="assessment-offers" id="offers" aria-labelledby="offers-title">
            <div className="public-section-heading"><span className="section-kicker">Персональный подбор</span><h2 id="offers-title">Подходящие предложения</h2><p>Каждый платёж рассчитан отдельно по диапазону условий конкретного продукта.</p></div>
            {result.offers.length ? <>
              <OfferCard offer={result.offers[0]} recommended clicking={clicking === result.offers[0].offer_id} onOpen={() => openOffer(result.offers[0])} />
              <ComparisonBlock offer={result.offers[0]} />
              {result.offers.length > 1 ? <h3 className="other-offers-title">Другие подходящие предложения</h3> : null}
              <div className="alternative-offers-grid">{result.offers.slice(1).map((offer) => <OfferCard key={offer.offer_id} offer={offer} clicking={clicking === offer.offer_id} onOpen={() => openOffer(offer)} />)}</div>
              <button className="sticky-result-cta" type="button" onClick={() => document.getElementById("recommended-offer")?.scrollIntoView({ behavior: "smooth", block: "center" })}><Star size={17} /> Посмотреть лучшее предложение</button>
            </> : <NoOffers result={result} />}
          </section>
          {error ? <div className="form-error" role="alert"><AlertTriangle size={18} />{error}</div> : null}
          <div className="ad-boundary">Riskline не принимает кредитных решений. Финальное решение принимает банк. Предложения могут быть рекламными; сервис может получить вознаграждение за переход.</div>
        </main>
      )}

      {transition ? (
        <div className="partner-transition" role="dialog" aria-modal="true" aria-labelledby="partner-transition-title" aria-describedby="partner-transition-description">
          <div className="partner-transition-card">
            <Building2 size={30} aria-hidden="true" />
            <span className="section-kicker">Прозрачный переход</span>
            <h3 id="partner-transition-title">Вы переходите к партнёру</h3>
            <p><strong>{transition.partner}</strong> · {transition.offer}</p>
            <ul id="partner-transition-description">
              <li>Условия и решение определяет партнёр.</li>
              <li>Riskline учитывает переход, чтобы улучшать качество подбора.</li>
              <li>Riskline может получить вознаграждение за переход.</li>
            </ul>
            <button ref={transitionPrimaryRef} className="button button-dark button-full" type="button" onClick={() => window.location.assign(transition.url)}>Продолжить у партнёра <ArrowRight size={17} /></button>
            <button className="button button-ghost button-full" type="button" onClick={() => setTransition(null)}>Вернуться к сравнению</button>
          </div>
        </div>
      ) : null}

      <TrustBlocks />
    </div>
  );
}

function SelectField({ id, label, help, value, options, onChange }: { id: string; label: string; help: string; value: string; options: string[][]; onChange: (value: string) => void }) {
  const helpId = `${id}-help`;
  return <label className="field-label" htmlFor={id}>{label}<select id={id} value={value} onChange={(event) => onChange(event.target.value)} aria-describedby={helpId}>{options.map(([optionValue, text]) => <option value={optionValue} key={optionValue}>{text}</option>)}</select><small id={helpId}>{help}</small></label>;
}

function NumberField({ id, label, help, value, onChange, ...props }: { id: string; label: string; help: string; value: string; onChange: (value: string) => void; min?: number; max?: number; step?: number }) {
  const helpId = `${id}-help`;
  return <label className="field-label" htmlFor={id}>{label}<NumericInput id={id} value={value} onValueChange={onChange} aria-describedby={helpId} {...props} /><small id={helpId}>{help}</small></label>;
}

function ProfileSummary({ result, profile: sourceProfile }: { result: OfferMatchResult; profile: CreditProfileInput }) {
  const profile = result.profile_result;
  const income = sourceProfile.monthly_income ?? 0;
  const existing = sourceProfile.existing_monthly_payments ?? 0;
  const remainingBudget = income - existing - (profile.estimated_monthly_payment ?? 0);
  const profileLabel = {
    strong: "Устойчивый профиль",
    stable: "Умеренный профиль",
    constrained: "Ограниченный профиль",
    high_attention: "Профиль требует внимания",
    insufficient_data: "Недостаточно данных",
  }[profile.profile_band] ?? "Предварительный профиль";
  const warnings = [
    ...(profile.confidence_level === "low" || profile.confidence_level === "basic" ? ["Уверенность ограничена коротким профилем или неизвестными полями."] : []),
    ...(profile.pti_band === "high" || profile.pti_band === "very_high" ? ["Расчётная долговая нагрузка повышена."] : []),
    ...(profile.profile_bands?.credit_history_band === "unknown" ? ["Кредитная история не указана."] : []),
    "Данные БКИ и документы банка не используются.",
  ];
  return (
    <article className="profile-summary-card riskline-profile-card assessment-profile-hero" id="riskline-profile">
      <div className="riskline-profile-heading">
        <div><span className="section-kicker light">Ваш профиль Riskline</span><h2>{profileLabel}</h2><p>Оценка объединяет финансовый расчёт, долговую нагрузку и модельный сигнал по указанным данным.</p></div>
        <div className={`riskline-index ${profile.model_available ? "is-active" : "is-fallback"}`} aria-label={`Riskline Index ${profile.riskline_index ?? "не рассчитан"} из 100`}>
          <strong>{profile.riskline_index ?? "—"}</strong><span>/ 100</span>
        </div>
      </div>
      <div className="riskline-index-scale" aria-hidden="true"><i style={{ width: `${profile.riskline_index ?? 0}%` }} /><span /><span /><span /></div>
      <p className="riskline-index-note">{profile.model_available ? "Персонализированная модельная оценка выполнена по указанным данным." : "Персонализированная оценка не выполнена; показан расчёт и совместимость по правилам."} Riskline Index — внутренний ориентир сервиса. Это не рейтинг БКИ и не предсказание решения банка.</p>
      <div className="profile-summary-grid">
        <div><span>Долговая нагрузка</span><strong>{profile.pti_value === null ? "—" : formatPercent(profile.pti_value, 0)}</strong><small>{bandLabels[profile.pti_band] ?? profile.pti_band}</small></div>
        <div><span>Платёж</span><strong>{profile.estimated_monthly_payment === null ? "—" : `${money.format(Math.round(profile.estimated_monthly_payment))} ₽`}</strong><small>ориентировочно</small></div>
        <div><span>После кредитных платежей</span><strong>{income ? `${money.format(Math.round(remainingBudget))} ₽` : "—"}</strong><small>из указанного личного дохода</small></div>
        <div><span>Совместимые предложения</span><strong>{result.total_eligible_offers}</strong><small>в текущем демо-каталоге</small></div>
      </div>
      <p className="remaining-budget-note">Остаток равен указанному личному доходу минус текущие и новый кредитные платежи. Аренда, продукты, коммунальные и другие повседневные расходы не учтены.</p>
      {warnings.map((warning) => <p className="profile-warning" key={warning}><AlertTriangle size={14} aria-hidden="true" />{warning}</p>)}
      <p className="profile-final-note">Финальное решение принимает банк.</p>
    </article>
  );
}

function ProfileFactors({ result }: { result: OfferMatchResult }) {
  const { strengths, limiting_factors: limitations } = result.profile_result;
  if (!strengths.length && !limitations.length) return null;
  return (
    <section className="profile-factors" aria-labelledby="profile-factors-title">
      <div className="public-section-heading"><span className="section-kicker">Объяснение результата</span><h3 id="profile-factors-title">Что влияет на текущий сценарий</h3><p>Цвет показывает направление оценки Riskline, а не решение банка.</p></div>
      <div className="factor-columns">
        <article><h4><CheckCircle2 size={18} /> Что помогает текущему сценарию</h4>{strengths.map((factor) => <div className="factor-line is-strength" key={factor.code}><div><strong>{factor.label}</strong><b>{factor.source === "ml_explanation" ? "Фактор модели" : "Финансовый фактор"}</b></div><span>{factor.message}</span></div>)}</article>
        <article><h4><AlertTriangle size={18} /> Что ограничивает текущий сценарий</h4>{limitations.map((factor) => <div className="factor-line is-limit" key={factor.code}><div><strong>{factor.label}</strong><b>{factor.source === "ml_explanation" ? "Фактор модели" : "Финансовый фактор"}</b></div><span>{factor.message}</span></div>)}</article>
      </div>
    </section>
  );
}

function ImprovementPanel({ result, scenarios, onApply, loading }: { result: OfferMatchResult; scenarios: ImprovementScenario[]; onApply: (amount: number, term: number, payments: number, factor: ImprovementScenario["factor"]) => Promise<void>; loading: boolean }) {
  if (!scenarios.length) return null;
  return (
    <section className="improvement-panel" aria-labelledby="improvement-title">
      <div className="public-section-heading"><span className="section-kicker">Практические сценарии</span><h2 id="improvement-title">Как можно улучшить сценарий</h2><p>Мы пересчитываем только параметры, которыми можно управлять. Доход, занятость и другие сведения нельзя искажать ради результата.</p></div>
      <div className="improvement-grid">
        {scenarios.map((scenario) => <article key={scenario.scenario_id}>
          <Sparkles size={18} aria-hidden="true" /><h4>{scenario.title}</h4>
          <div className="scenario-before-after"><span>Сейчас <strong>{scenario.current_state}</strong></span><ArrowRight size={15} /><span>Сценарий <strong>{scenario.suggested_state}</strong></span></div>
          <dl className="scenario-metric-delta">
            <div><dt>Riskline Index</dt><dd>{result.profile_result.riskline_index ?? "—"} → {scenario.riskline_index ?? "—"}</dd></div>
            <div><dt>Платёж</dt><dd>{money.format(Math.round(result.profile_result.estimated_monthly_payment ?? 0))} → {money.format(Math.round(scenario.estimated_monthly_payment))} ₽</dd></div>
            <div><dt>Нагрузка</dt><dd>{result.profile_result.pti_value === null ? "—" : formatPercent(result.profile_result.pti_value, 0)} → {scenario.pti_value === null ? "—" : formatPercent(scenario.pti_value, 0)}</dd></div>
            <div><dt>Предложения</dt><dd>{result.total_eligible_offers} → {scenario.eligible_offer_count}</dd></div>
          </dl>
          <ul>{scenario.effects.map((effect) => <li key={effect}>{effect}</li>)}</ul>
          <p><strong>Компромисс:</strong> {scenario.trade_off}</p>
          <button className="button button-ghost button-full" type="button" disabled={loading} onClick={() => onApply(scenario.amount, scenario.term_months, scenario.existing_monthly_payments, scenario.factor)}>Применить сценарий</button>
        </article>)}
      </div>
    </section>
  );
}

function ScenarioSimulator({ profile, result, previousResult, onApply, loading, sessionId }: { profile: CreditProfileInput; result: OfferMatchResult; previousResult: OfferMatchResult | null; onApply: (amount: number, term: number, payments: number, factor: ImprovementScenario["factor"]) => Promise<void>; loading: boolean; sessionId: string }) {
  const initialAmount = profile.requested_amount ?? amountForBand(profile.requested_amount_band);
  const [amount, setAmount] = useState(String(Math.round(initialAmount)));
  const [term, setTerm] = useState(String(profile.term_months));
  const [payments, setPayments] = useState(String(profile.existing_monthly_payments ?? 0));
  const apply = () => {
    const nextAmount = Number(amount);
    const nextTerm = Number(term);
    const nextPayments = Number(payments);
    if (!Number.isFinite(nextAmount) || nextAmount <= 0 || !Number.isInteger(nextTerm) || nextTerm < 3 || nextTerm > 120 || !Number.isFinite(nextPayments) || nextPayments < 0) return;
    void recordPublicEvent("scenario_started", "scenario", sessionId, { scenario_type: "amount", profile_band: result.profile_result.profile_band, pti_band: result.profile_result.pti_band }).catch(() => undefined);
    void onApply(nextAmount, nextTerm, nextPayments, "amount");
  };
  return (
    <section className="scenario-simulator" aria-labelledby="simulator-title">
      <div><span className="section-kicker">Интерактивный сценарий</span><h3 id="simulator-title"><SlidersHorizontal size={20} /> Проверьте другие параметры</h3><p>Изменения не сохраняются в браузере. Пересчёт показывает направление профиля, а не обещание решения банка.</p></div>
      {previousResult ? <div className="simulator-comparison" aria-label="Сравнение сценариев"><ScenarioSnapshot label="Было" result={previousResult} /><ArrowRight size={20} /><ScenarioSnapshot label="Новый сценарий" result={result} /></div> : null}
      <div className="scenario-controls">
        <NumberField id="scenario-amount" label="Сумма, ₽" help="Измените сумму для сравнения." value={amount} onChange={setAmount} min={1} />
        <NumberField id="scenario-term" label="Срок, месяцев" help="От 3 до 120 месяцев." value={term} onChange={setTerm} min={3} max={120} step={1} />
        <NumberField id="scenario-payments" label="Текущие платежи, ₽" help="Укажите честную оценку нагрузки." value={payments} onChange={setPayments} min={0} />
      </div>
      <button className="button button-dark" type="button" onClick={apply} disabled={loading}>{loading ? "Пересчитываем…" : "Применить сценарий"}</button>
    </section>
  );
}

function ScenarioSnapshot({ label, result }: { label: string; result: OfferMatchResult }) {
  return <article><span>{label}</span><strong>Оценка Riskline {result.profile_result.riskline_index ?? "—"}</strong><small>Платёж {money.format(Math.round(result.profile_result.estimated_monthly_payment ?? 0))} ₽ · нагрузка {result.profile_result.pti_value === null ? "—" : formatPercent(result.profile_result.pti_value, 0)} · предложений {result.total_eligible_offers}</small></article>;
}

function OfferCard({ offer, clicking, onOpen, recommended = false }: { offer: RankedOffer; clicking: boolean; onOpen: () => void; recommended?: boolean }) {
  const calculation = offer.calculation;
  const paymentText = calculation?.monthly_payment_min !== null && calculation?.monthly_payment_min !== undefined
    ? `${money.format(Math.round(calculation.monthly_payment_min))}${calculation.monthly_payment_max && calculation.monthly_payment_max !== calculation.monthly_payment_min ? `–${money.format(Math.round(calculation.monthly_payment_max))}` : ""} ₽/мес.`
    : null;
  return (
    <article className={`offer-card public-offer-card ${recommended ? "is-recommended" : ""}`} id={recommended ? "recommended-offer" : undefined}>
      <div className="offer-rank">{recommended ? <><Star size={14} /> Рекомендуемое предложение</> : `Вариант ${offer.rank}`}</div>
      <div className="offer-card-copy">
        <div className="offer-brand-line"><span className="offer-initials">{offer.advertiser_name.slice(0, 2).toUpperCase()}</span><span>{offer.advertiser_name}</span>{offer.is_demo ? <b>Демо-предложение</b> : null}</div>
        <h3>{offer.product_name}</h3>
        <p>{productLabels[offer.product_type] ?? offer.product_type}</p>
        {offer.main_benefit ? <strong className="offer-main-benefit">{offer.main_benefit}</strong> : null}
        <div className="offer-compatibility">{offer.profile_compatibility}</div>
        {paymentText ? <div className="offer-payment"><span>Расчёт по условиям предложения</span><strong>{paymentText}</strong></div> : null}
        {calculation ? <div className="offer-calculation-facts"><span>Сумма: {money.format(calculation.selected_amount)} ₽</span><span>Срок: {calculation.selected_term_months} мес.</span>{calculation.annual_rate_min !== null ? <span>Годовая ставка: {calculation.annual_rate_min}–{calculation.annual_rate_max ?? calculation.annual_rate_min}%</span> : null}</div> : null}
        {calculation?.overpayment_min !== null && calculation?.overpayment_min !== undefined ? <div className="offer-overpayment">Переплата по диапазону: {money.format(Math.round(calculation.overpayment_min))}–{money.format(Math.round(calculation.overpayment_max ?? calculation.overpayment_min))} ₽</div> : null}
        {calculation?.adjustments.map((adjustment) => <div className="offer-adjustment" key={adjustment}>{adjustment}</div>)}
        <div className="offer-range">{money.format(offer.min_amount)}–{money.format(offer.max_amount)} ₽ · {offer.min_term_months}–{offer.max_term_months} мес.</div>
        <small>Уверенность: {confidenceLabels[offer.confidence_level] ?? offer.confidence_level}</small>
        {offer.positive_reasons.map((reason) => <em key={reason}><CheckCircle2 size={13} aria-hidden="true" />{reason}</em>)}
        {offer.warnings.map((warning) => <i key={warning}><AlertTriangle size={13} aria-hidden="true" />{warning}</i>)}
        {offer.full_cost_range_text ? <div className="offer-full-cost"><strong>Полная стоимость кредита:</strong> {offer.full_cost_range_text}</div> : null}
        <div className="offer-disclosure"><strong>{offer.ad_disclosure}</strong><span>{offer.legal_disclaimer}</span></div>
      </div>
      <button className="button button-dark" type="button" onClick={onOpen} disabled={clicking}>
        {clicking ? <LoaderCircle className="spin" size={17} aria-hidden="true" /> : <ArrowRight size={17} aria-hidden="true" />}
        {clicking ? "Готовим переход…" : offer.cta_text}
      </button>
    </article>
  );
}

function NoOffers({ result }: { result: OfferMatchResult }) {
  return (
    <div className="offer-empty no-offers"><AlertTriangle size={24} aria-hidden="true" /><strong>Пока не нашли подходящего предложения</strong><span>{result.user_explanation} Это не означает решение банка.</span><ul>{result.suggestions.map((suggestion) => <li key={suggestion}>{suggestion}</li>)}<li>Проверьте предложения позже — каталог может обновиться.</li></ul><small>Результат относится только к указанным параметрам и может измениться после их уточнения.</small></div>
  );
}

function WhatYouGet() {
  return (
    <div className="what-you-get">
      <CheckCircle2 size={28} aria-hidden="true" />
      <span className="section-kicker">Что вы получите</span>
      <h3>Персональная оценка без банковской анкеты</h3>
      <ul>
        <li>Riskline Index и профиль</li>
        <li>Что помогает и ограничивает результат</li>
        <li>Сценарии, которые можно проверить</li>
        <li>Подходящие предложения с отдельным расчётом</li>
      </ul>
      <small>Финальное решение принимает банк.</small>
    </div>
  );
}

function AssessmentLoading() {
  return <div className="assessment-loading" role="status"><LoaderCircle className="spin" size={32} /><h2>Анализируем профиль</h2><ul><li>Считаем долговую нагрузку</li><li>Сравниваем факторы профиля</li><li>Проверяем совместимые предложения</li></ul></div>;
}

function CreditHistoryAdvice({ band }: { band: CreditProfileInput["credit_history_band"] }) {
  if (!["minor_overdues", "serious_overdues", "no_history"].includes(band)) return null;
  const copy = band === "no_history"
    ? "Отсутствие истории не означает автоматический отказ. Своевременное выполнение будущих обязательств постепенно формирует историю."
    : "Перед новой заявкой полезно проверить кредитную историю на ошибки и продолжать своевременно выполнять текущие обязательства.";
  return <article className="credit-history-advice"><BookOpenCheck size={21} /><div><strong>О кредитной истории</strong><p>{copy} Riskline не получает данные БКИ и не знает внутренних правил банка.</p></div></article>;
}

function employmentLabel(value: CreditProfileInput["employment_type"]): string {
  return {
    employee: "По найму",
    self_employed: "Самозанятый",
    individual_entrepreneur: "ИП",
    pensioner: "Пенсионер",
    unofficial: "Неофициальная занятость",
    unemployed: "Не работаю",
    unknown: "Не указано",
  }[value];
}

function ComparisonBlock({ offer }: { offer: RankedOffer }) {
  const reasons = offer.positive_reasons.slice(0, 4);
  return (
    <article className="recommendation-explainer">
      <span className="section-kicker">Почему этот вариант первый</span>
      <h3>Лучшее сочетание по указанным параметрам</h3>
      <ul>
        {reasons.map((reason) => <li key={reason}><CheckCircle2 size={15} />{reason}</li>)}
        <li><CheckCircle2 size={15} />Меньше предупреждений среди подходящих вариантов</li>
      </ul>
      <p>Разница в платеже и условиях между вариантами может быть существенной. Сравните предложения перед подачей заявки.</p>
    </article>
  );
}

function TrustBlocks() {
  const items = [
    ["Как считается платёж", "Аннуитетный платёж распределяет основной долг и проценты на равные примерные платежи. Страховки и комиссии в оценку не входят."],
    ["Что такое долговая нагрузка", "Это отношение примерных текущих и новых ежемесячных платежей к доходу. Высокое значение может снизить комфорт бюджета, но не является решением банка."],
    ["Как работает подбор", "Сначала сервис исключает несовместимые варианты, затем сравнивает комфорт платежа, сумму, срок и цель. Вознаграждение партнёра не определяет рекомендацию само по себе."],
    ["Почему результат предварительный", "Сервис не получает БКИ, документы и результаты банковской проверки. Финальное решение всегда принимает банк."],
  ];
  return <section className="trust-section" aria-labelledby="trust-title"><div className="public-section-heading"><span className="section-kicker">Понятно о расчёте</span><h3 id="trust-title">Что важно знать о результате</h3></div><div className="trust-grid">{items.map(([title, copy]) => <article key={title}><BookOpenCheck size={20} aria-hidden="true" /><h4>{title}</h4><p>{copy}</p></article>)}</div></section>;
}
