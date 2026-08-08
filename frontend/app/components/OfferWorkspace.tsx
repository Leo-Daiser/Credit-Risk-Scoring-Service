"use client";

import {
  AlertTriangle,
  ArrowRight,
  BadgePercent,
  BookOpenCheck,
  CheckCircle2,
  LoaderCircle,
  ShieldCheck,
} from "lucide-react";
import { useState } from "react";
import type { CreditProfileInput, OfferMatchResult, RankedOffer } from "../lib/api";
import { apiFetch, formatPercent } from "../lib/api";
import { createAnonymousSessionId } from "../lib/public-analytics";
import { NumericInput } from "./NumericInput";

const initialProfile: CreditProfileInput = {
  age_band: "31_45",
  income_band: "50k_100k",
  employment_type: "employee",
  requested_amount_band: "100k_300k",
  term_months: 24,
  existing_monthly_payments_band: "zero",
  credit_history_band: "average",
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

export function OfferWorkspace() {
  const [sessionId] = useState(createAnonymousSessionId);
  const [profile, setProfile] = useState(initialProfile);
  const [termDraft, setTermDraft] = useState("24");
  const [amountDraft, setAmountDraft] = useState("");
  const [paymentsDraft, setPaymentsDraft] = useState("");
  const [result, setResult] = useState<OfferMatchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [clicking, setClicking] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const update = <K extends keyof CreditProfileInput>(key: K, value: CreditProfileInput[K]) => {
    setProfile((current) => ({ ...current, [key]: value }));
  };

  const submit = async () => {
    const term = Number(termDraft);
    const amount = amountDraft === "" ? undefined : Number(amountDraft);
    const payments = paymentsDraft === "" ? undefined : Number(paymentsDraft);
    if (!Number.isInteger(term) || term < 3 || term > 120) {
      setError("Срок должен быть целым числом от 3 до 120 месяцев.");
      return;
    }
    if (amount !== undefined && (!Number.isFinite(amount) || amount <= 0 || amount > 10_000_000)) {
      setError("Точная сумма должна быть от 1 до 10 000 000 ₽ или оставлена пустой.");
      return;
    }
    if (payments !== undefined && (!Number.isFinite(payments) || payments < 0 || payments > 2_000_000)) {
      setError("Текущие платежи должны быть от 0 до 2 000 000 ₽.");
      return;
    }
    if (!profile.consent_to_process) {
      setError("Для подбора необходимо согласие на обработку введённых диапазонов.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const submittedProfile: CreditProfileInput = {
        ...profile,
        term_months: term,
        ...(amount === undefined ? {} : {
          requested_amount: amount,
          requested_amount_band: amountBandFor(amount),
        }),
        ...(payments === undefined ? {} : {
          existing_monthly_payments: payments,
          existing_monthly_payments_band: paymentsBandFor(payments),
        }),
      };
      const response = await apiFetch<OfferMatchResult>("v1/offers/match", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Anonymous-Session-ID": sessionId },
        body: JSON.stringify({
          profile: submittedProfile,
          context: { anonymous_session_id: sessionId, source: "public_matching" },
          limit: 5,
        }),
      });
      setProfile(submittedProfile);
      setResult(response);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Подбор не выполнен. Попробуйте ещё раз.");
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
      window.location.assign(click.redirect_url);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Переход не выполнен. Попробуйте ещё раз.");
      setClicking(null);
    }
  };

  return (
    <div className="offers-page">
      <section className="offers-intro">
        <div>
          <span className="section-kicker">Короткий профиль без документов</span>
          <h2>Предварительный профиль и совместимые предложения.</h2>
          <p>Можно указать примерные значения. Чем больше неизвестных полей, тем ниже уверенность результата. Паспорт, телефон, имя, документы, работодатель и данные БКИ не запрашиваются. Финальное решение принимает банк.</p>
        </div>
        <div className="privacy-chip"><ShieldCheck size={20} aria-hidden="true" /> Точные суммы используются только в текущем запросе</div>
      </section>

      <section className="offers-layout">
        <article className="panel offer-profile-form">
          <div className="panel-heading"><div><span className="section-kicker">Privacy-light profile</span><h3>Параметры подбора</h3></div></div>
          <div className="offer-fields">
            <SelectField id="offer-age" label="Возрастной диапазон" help="Нужен для проверки базовых возрастных ограничений." value={profile.age_band} onChange={(value) => update("age_band", value as CreditProfileInput["age_band"])} options={[["18_21", "18–21"], ["22_30", "22–30"], ["31_45", "31–45"], ["46_60", "46–60"], ["60_plus", "Старше 60"]]} />
            <SelectField id="offer-income" label="Доход в месяц" help="Достаточно примерного диапазона; точный доход не нужен." value={profile.income_band} onChange={(value) => update("income_band", value as CreditProfileInput["income_band"])} options={[["lt_50k", "До 50 тыс."], ["50k_100k", "50–100 тыс."], ["100k_150k", "100–150 тыс."], ["150k_250k", "150–250 тыс."], ["gt_250k", "Более 250 тыс."], ["unknown", "Не знаю / не указывать"]]} />
            <SelectField id="offer-employment" label="Тип занятости" help="Используется только как категория совместимости." value={profile.employment_type} onChange={(value) => update("employment_type", value as CreditProfileInput["employment_type"])} options={[["employee", "По найму"], ["self_employed", "Самозанятый"], ["individual_entrepreneur", "ИП"], ["pensioner", "Пенсионер"], ["unofficial", "Неофициально"], ["unemployed", "Без работы"], ["unknown", "Не знаю / не указывать"]]} />
            <SelectField id="offer-amount-band" label="Диапазон суммы" help="По нему проверяются лимиты продукта." value={profile.requested_amount_band} onChange={(value) => { update("requested_amount_band", value as CreditProfileInput["requested_amount_band"]); setAmountDraft(""); }} options={[["lt_100k", "До 100 тыс."], ["100k_300k", "100–300 тыс."], ["300k_700k", "300–700 тыс."], ["700k_1_5m", "700 тыс.–1,5 млн"], ["gt_1_5m", "Более 1,5 млн"]]} />
            <NumberField id="offer-exact-amount" label="Точная сумма, ₽ — необязательно" help="Только для текущего расчёта; не сохраняется." value={amountDraft} onChange={setAmountDraft} min={1} />
            <NumberField id="offer-term-months" label="Срок, месяцев" help="Проверяет совместимость со сроком оффера." value={termDraft} onChange={setTermDraft} min={3} max={120} step={1} />
            <SelectField id="offer-payments-band" label="Текущие платежи" help="Нужны для приблизительной оценки PTI." value={profile.existing_monthly_payments_band} onChange={(value) => { update("existing_monthly_payments_band", value as CreditProfileInput["existing_monthly_payments_band"]); setPaymentsDraft(""); }} options={[["zero", "Нет"], ["lt_10k", "До 10 тыс."], ["10k_30k", "10–30 тыс."], ["30k_60k", "30–60 тыс."], ["gt_60k", "Более 60 тыс."], ["unknown", "Не знаю / не указывать"]]} />
            <NumberField id="offer-exact-payments" label="Точный платёж, ₽ — необязательно" help="Только для текущего расчёта; не сохраняется." value={paymentsDraft} onChange={setPaymentsDraft} min={0} />
            <SelectField id="offer-history" label="Кредитная история" help="Самооценка диапазона; БКИ не запрашивается." value={profile.credit_history_band} onChange={(value) => update("credit_history_band", value as CreditProfileInput["credit_history_band"])} options={[["good", "Хорошая"], ["average", "Средняя"], ["minor_overdues", "Небольшие просрочки"], ["serious_overdues", "Серьёзные просрочки"], ["no_history", "Нет истории"], ["unknown", "Не знаю / не указывать"]]} />
            <SelectField id="offer-purpose" label="Цель кредита" help="Помогает поднять релевантный тип продукта." value={profile.loan_purpose} onChange={(value) => update("loan_purpose", value as CreditProfileInput["loan_purpose"])} options={[["cash", "Наличные"], ["refinance", "Рефинансирование"], ["car", "Автомобиль"], ["repair", "Ремонт"], ["education", "Образование"], ["medical", "Лечение"], ["other", "Другое"]]} />
          </div>
          <label className="consent-row" htmlFor="offer-consent">
            <input id="offer-consent" type="checkbox" checked={profile.consent_to_process} onChange={(event) => update("consent_to_process", event.target.checked)} aria-describedby="offer-consent-help" />
            <span id="offer-consent-help">Согласен на обработку введённых диапазонов для предварительного профиля и подбора. Это не кредитное решение.</span>
          </label>
          <label className="consent-row secondary-consent" htmlFor="offer-ad-consent">
            <input id="offer-ad-consent" type="checkbox" checked={profile.consent_to_ad_personalization} onChange={(event) => update("consent_to_ad_personalization", event.target.checked)} />
            <span>Разрешаю персонализацию рекламных предложений.</span>
          </label>
          {error ? <div className="form-error" role="alert" id="offer-form-error"><AlertTriangle size={18} aria-hidden="true" /> {error}</div> : null}
          <button className="button button-dark button-full" type="button" onClick={submit} disabled={loading} aria-describedby="offer-form-error">
            {loading ? <LoaderCircle className="spin" size={18} aria-hidden="true" /> : <BadgePercent size={18} aria-hidden="true" />}
            {loading ? "Выполняем предварительный подбор…" : "Получить профиль и предложения"}
          </button>
          <p className="model-disclaimer">Сервис не принимает кредитных решений. Финальное решение принимает банк; предложения могут быть рекламными.</p>
        </article>

        <aside className="offer-results" aria-live="polite">
          {loading && !result ? <div className="offer-empty initial"><LoaderCircle className="spin" size={27} aria-hidden="true" /><strong>Подбираем совместимые предложения</strong><span>Проверяем диапазоны и считаем предварительную нагрузку.</span></div> : null}
          {!loading && result ? (
            <>
              <ProfileSummary result={result} />
              {result.offers.length ? result.offers.map((offer) => (
                <OfferCard key={offer.offer_id} offer={offer} clicking={clicking === offer.offer_id} onOpen={() => openOffer(offer)} />
              )) : <NoOffers result={result} />}
              <div className="ad-boundary">Сервис не принимает кредитных решений. Финальное решение принимает банк. Предложения могут быть рекламными; сервис может получить вознаграждение за переход.</div>
            </>
          ) : null}
          {!loading && !result ? <div className="offer-empty initial"><CheckCircle2 size={27} aria-hidden="true" /><strong>Результат появится здесь</strong><span>Покажем предварительный профиль, PTI, уверенность и только допустимые предложения.</span></div> : null}
        </aside>
      </section>

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

function ProfileSummary({ result }: { result: OfferMatchResult }) {
  const profile = result.profile_result;
  const warnings = [
    ...(profile.confidence_level === "low" || profile.confidence_level === "basic" ? ["Уверенность ограничена коротким профилем или неизвестными полями."] : []),
    ...(profile.pti_band === "high" || profile.pti_band === "very_high" ? ["Расчётная долговая нагрузка повышена."] : []),
    ...(profile.profile_bands?.credit_history_band === "unknown" ? ["Кредитная история не указана."] : []),
    "Данные БКИ и банковский underwriting не используются.",
  ];
  return (
    <article className="profile-summary-card">
      <span className="section-kicker light">Предварительный профиль</span>
      <h3>Оценка по введённым данным</h3>
      <div className="profile-summary-grid">
        <div><span>Долговая нагрузка</span><strong>{profile.pti_value === null ? "—" : formatPercent(profile.pti_value, 0)}</strong><small>{bandLabels[profile.pti_band] ?? profile.pti_band}</small></div>
        <div><span>Платёж</span><strong>{profile.estimated_monthly_payment === null ? "—" : `${money.format(Math.round(profile.estimated_monthly_payment))} ₽`}</strong><small>ориентировочно</small></div>
        <div><span>Доступность</span><strong>{bandLabels[profile.affordability_band] ?? profile.affordability_band}</strong><small>по PTI</small></div>
        <div><span>Уверенность</span><strong>{confidenceLabels[profile.confidence_level] ?? profile.confidence_level}</strong><small>покрытие {formatPercent(profile.data_coverage, 0)}</small></div>
      </div>
      <p className="eligible-count">Совместимых предложений: <strong>{result.offers.length}</strong></p>
      {warnings.map((warning) => <p className="profile-warning" key={warning}><AlertTriangle size={14} aria-hidden="true" />{warning}</p>)}
      <p className="profile-final-note">Финальное решение принимает банк.</p>
    </article>
  );
}

function OfferCard({ offer, clicking, onOpen }: { offer: RankedOffer; clicking: boolean; onOpen: () => void }) {
  return (
    <article className="offer-card public-offer-card">
      <div className="offer-rank">#{offer.rank}</div>
      <div className="offer-card-copy">
        <span>{offer.advertiser_name}</span>
        <h3>{offer.product_name}</h3>
        <p>{productLabels[offer.product_type] ?? offer.product_type}</p>
        <div className="offer-range">{money.format(offer.min_amount)}–{money.format(offer.max_amount)} ₽ · {offer.min_term_months}–{offer.max_term_months} мес.</div>
        <small>Уверенность: {confidenceLabels[offer.confidence_level] ?? offer.confidence_level}</small>
        {offer.positive_reasons.map((reason) => <em key={reason}><CheckCircle2 size={13} aria-hidden="true" />{reason}</em>)}
        {offer.warnings.map((warning) => <i key={warning}><AlertTriangle size={13} aria-hidden="true" />{warning}</i>)}
        <div className="offer-disclosure">{offer.disclosure}</div>
      </div>
      <button className="button button-dark" type="button" onClick={onOpen} disabled={clicking}>
        {clicking ? <LoaderCircle className="spin" size={17} aria-hidden="true" /> : <ArrowRight size={17} aria-hidden="true" />}
        {clicking ? "Открываем…" : "Посмотреть условия у партнёра"}
      </button>
    </article>
  );
}

function NoOffers({ result }: { result: OfferMatchResult }) {
  return (
    <div className="offer-empty no-offers"><AlertTriangle size={24} aria-hidden="true" /><strong>Сейчас нет совместимых предложений</strong><span>{result.user_explanation}</span><ul>{result.suggestions.map((suggestion) => <li key={suggestion}>{suggestion}</li>)}<li>Проверьте предложения позже — каталог может обновиться.</li></ul><small>Это не означает отказ банка и не характеризует вас как заёмщика.</small></div>
  );
}

function TrustBlocks() {
  const items = [
    ["Как считается платёж", "Аннуитетный платёж распределяет основной долг и проценты на равные примерные платежи. Страховки и комиссии в оценку не входят."],
    ["Что такое долговая нагрузка", "PTI — примерные текущие и новые месячные кредитные платежи, разделённые на доход. Высокое значение может снизить комфорт бюджета, но не является решением банка."],
    ["Как работает подбор", "Hard eligibility rules сначала фильтруют предложения. Затем risk profile и affordability помогают ranking; он не строится только на вознаграждении."],
    ["Почему результат предварительный", "Сервис не получает БКИ, документы и банковский underwriting. Партнёрские outcomes могут улучшить будущий ranking, но финальное решение всегда принимает банк."],
  ];
  return <section className="trust-section" aria-labelledby="trust-title"><div className="public-section-heading"><span className="section-kicker">Понятно о расчёте</span><h3 id="trust-title">Что важно знать о результате</h3></div><div className="trust-grid">{items.map(([title, copy]) => <article key={title}><BookOpenCheck size={20} aria-hidden="true" /><h4>{title}</h4><p>{copy}</p></article>)}</div></section>;
}
