"use client";

import {
  AlertTriangle,
  ArrowRight,
  BadgePercent,
  Building2,
  BookOpenCheck,
  CheckCircle2,
  LoaderCircle,
  ShieldCheck,
  Star,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
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
  const [transition, setTransition] = useState<{ url: string; partner: string; offer: string } | null>(null);
  const [showRecovery, setShowRecovery] = useState(false);
  const [recoveryDismissed, setRecoveryDismissed] = useState(false);

  useEffect(() => {
    if (!result?.offers.length || recoveryDismissed) return;
    const onVisibility = () => {
      if (document.visibilityState === "visible") setShowRecovery(true);
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [result, recoveryDismissed]);

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
      setTransition({
        url: click.redirect_url,
        partner: offer.advertiser_name,
        offer: offer.product_name,
      });
      setClicking(null);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Переход не выполнен. Попробуйте ещё раз.");
      setClicking(null);
    }
  };

  return (
    <div className="offers-page">
      <section className="offers-intro">
        <div>
          <span className="section-kicker">Предварительный подбор</span>
          <h1>Подберите предложения под ваш платёж и долговую нагрузку.</h1>
          <p>Можно указать примерные значения. Чем больше неизвестных полей, тем ниже уверенность результата. Паспорт, телефон, имя, документы, работодатель и данные БКИ не запрашиваются. Финальное решение принимает банк.</p>
        </div>
        <div className="privacy-chip"><ShieldCheck size={20} aria-hidden="true" /> Точные суммы используются только во время расчёта</div>
      </section>

      <section className={`offers-layout ${result ? "has-results" : ""}`}>
        <article className="panel offer-profile-form">
          <div className="panel-heading"><div><span className="section-kicker">Три коротких шага</span><h3>Расскажите о нужном варианте</h3></div></div>
          <div className="offer-form-steps">
            <fieldset className="offer-form-step">
              <legend><span>1</span><strong>Что вам нужно?</strong></legend>
              <div className="offer-fields">
                <SelectField id="offer-amount-band" label="Диапазон суммы" help="По нему проверяются лимиты предложения." value={profile.requested_amount_band} onChange={(value) => { update("requested_amount_band", value as CreditProfileInput["requested_amount_band"]); setAmountDraft(""); }} options={[["lt_100k", "До 100 тыс."], ["100k_300k", "100–300 тыс."], ["300k_700k", "300–700 тыс."], ["700k_1_5m", "700 тыс.–1,5 млн"], ["gt_1_5m", "Более 1,5 млн"]]} />
                <NumberField id="offer-term-months" label="Срок, месяцев" help="Нужен для сравнения доступных сроков." value={termDraft} onChange={setTermDraft} min={3} max={120} step={1} />
                <SelectField id="offer-purpose" label="Цель" help="Помогает показать более подходящий тип продукта." value={profile.loan_purpose} onChange={(value) => update("loan_purpose", value as CreditProfileInput["loan_purpose"])} options={[["cash", "Наличные"], ["refinance", "Рефинансирование"], ["car", "Автомобиль"], ["repair", "Ремонт"], ["education", "Образование"], ["medical", "Лечение"], ["other", "Другое"]]} />
              </div>
              <details className="precision-fields"><summary>Указать сумму точнее</summary><NumberField id="offer-exact-amount" label="Точная сумма, ₽ — необязательно" help="Используется только для текущего расчёта и не сохраняется." value={amountDraft} onChange={setAmountDraft} min={1} /></details>
            </fieldset>
            <fieldset className="offer-form-step">
              <legend><span>2</span><strong>Немного о вас</strong></legend>
              <div className="offer-fields">
                <SelectField id="offer-age" label="Возраст" help="Для базовых возрастных ограничений." value={profile.age_band} onChange={(value) => update("age_band", value as CreditProfileInput["age_band"])} options={[["18_21", "18–21"], ["22_30", "22–30"], ["31_45", "31–45"], ["46_60", "46–60"], ["60_plus", "Старше 60"]]} />
                <SelectField id="offer-income" label="Доход в месяц" help="Достаточно примерного диапазона." value={profile.income_band} onChange={(value) => update("income_band", value as CreditProfileInput["income_band"])} options={[["lt_50k", "До 50 тыс."], ["50k_100k", "50–100 тыс."], ["100k_150k", "100–150 тыс."], ["150k_250k", "150–250 тыс."], ["gt_250k", "Более 250 тыс."], ["unknown", "Не знаю / не указывать"]]} />
                <SelectField id="offer-employment" label="Занятость" help="Используется как категория совместимости." value={profile.employment_type} onChange={(value) => update("employment_type", value as CreditProfileInput["employment_type"])} options={[["employee", "По найму"], ["self_employed", "Самозанятый"], ["individual_entrepreneur", "ИП"], ["pensioner", "Пенсионер"], ["unofficial", "Неофициально"], ["unemployed", "Без работы"], ["unknown", "Не знаю / не указывать"]]} />
              </div>
            </fieldset>
            <fieldset className="offer-form-step">
              <legend><span>3</span><strong>Текущая нагрузка</strong></legend>
              <div className="offer-fields">
                <SelectField id="offer-payments-band" label="Текущие платежи" help="Для приблизительной оценки нагрузки." value={profile.existing_monthly_payments_band} onChange={(value) => { update("existing_monthly_payments_band", value as CreditProfileInput["existing_monthly_payments_band"]); setPaymentsDraft(""); }} options={[["zero", "Нет"], ["lt_10k", "До 10 тыс."], ["10k_30k", "10–30 тыс."], ["30k_60k", "30–60 тыс."], ["gt_60k", "Более 60 тыс."], ["unknown", "Не знаю / не указывать"]]} />
                <SelectField id="offer-history" label="Кредитная история" help="Самооценка; данные БКИ не запрашиваются." value={profile.credit_history_band} onChange={(value) => update("credit_history_band", value as CreditProfileInput["credit_history_band"])} options={[["good", "Хорошая"], ["average", "Средняя"], ["minor_overdues", "Небольшие просрочки"], ["serious_overdues", "Серьёзные просрочки"], ["no_history", "Нет истории"], ["unknown", "Не знаю / не указывать"]]} />
              </div>
              <details className="precision-fields"><summary>Указать текущий платёж точнее</summary><NumberField id="offer-exact-payments" label="Точный платёж, ₽ — необязательно" help="Используется только для текущего расчёта и не сохраняется." value={paymentsDraft} onChange={setPaymentsDraft} min={0} /></details>
            </fieldset>
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
            {loading ? "Подбираем предложения…" : "Показать предложения"}
          </button>
          <p className="model-disclaimer">Сервис не принимает кредитных решений. Финальное решение принимает банк; предложения могут быть рекламными.</p>
        </article>

        <aside className="offer-results" aria-live="polite">
          {loading && !result ? <div className="offer-empty initial"><LoaderCircle className="spin" size={27} aria-hidden="true" /><strong>Подбираем совместимые предложения</strong><span>Проверяем диапазоны и считаем предварительную нагрузку.</span></div> : null}
          {!loading && result ? (
            <>
              {showRecovery ? (
                <div className="exit-recovery" role="status">
                  <div><strong>Сравните предложения перед выходом</strong><span>Расчёт останется на странице, пока вкладка открыта.</span></div>
                  <button type="button" aria-label="Закрыть подсказку" onClick={() => { setShowRecovery(false); setRecoveryDismissed(true); }}><X size={16} /></button>
                </div>
              ) : null}
              <ProfileSummary result={result} />
              {result.offers.length ? (
                <>
                  <OfferCard
                    offer={result.offers[0]}
                    recommended
                    payment={result.profile_result.estimated_monthly_payment}
                    clicking={clicking === result.offers[0].offer_id}
                    onOpen={() => openOffer(result.offers[0])}
                  />
                  <ComparisonBlock offer={result.offers[0]} />
                  {profile.existing_monthly_payments_band !== "zero" ? (
                    <div className="refinance-trigger"><strong>Есть текущие платежи?</strong><span>Проверьте, может ли рефинансирование снизить ежемесячную нагрузку.</span></div>
                  ) : null}
                  {result.offers.length > 1 ? <h3 className="other-offers-title">Другие подходящие предложения</h3> : null}
                  {result.offers.slice(1).map((offer) => (
                    <OfferCard
                      key={offer.offer_id}
                      offer={offer}
                      payment={result.profile_result.estimated_monthly_payment}
                      clicking={clicking === offer.offer_id}
                      onOpen={() => openOffer(offer)}
                    />
                  ))}
                  <button className="sticky-result-cta" type="button" onClick={() => document.getElementById("recommended-offer")?.scrollIntoView({ behavior: "smooth", block: "center" })}>
                    <Star size={17} /> Посмотреть лучшее предложение
                  </button>
                </>
              ) : <NoOffers result={result} />}
              <div className="ad-boundary">Сервис не принимает кредитных решений. Финальное решение принимает банк. Предложения могут быть рекламными; сервис может получить вознаграждение за переход.</div>
            </>
          ) : null}
          {!loading && !result ? <WhatYouGet /> : null}
        </aside>
      </section>

      {transition ? (
        <div className="partner-transition" role="dialog" aria-modal="true" aria-labelledby="partner-transition-title">
          <div className="partner-transition-card">
            <Building2 size={30} aria-hidden="true" />
            <span className="section-kicker">Прозрачный переход</span>
            <h3 id="partner-transition-title">Вы переходите к партнёру</h3>
            <p><strong>{transition.partner}</strong> · {transition.offer}</p>
            <ul>
              <li>Условия и решение определяет партнёр.</li>
              <li>Riskline учитывает переход, чтобы улучшать качество подбора.</li>
              <li>Riskline может получить вознаграждение за переход.</li>
            </ul>
            <button className="button button-dark button-full" type="button" onClick={() => window.location.assign(transition.url)}>Продолжить у партнёра <ArrowRight size={17} /></button>
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

function ProfileSummary({ result }: { result: OfferMatchResult }) {
  const profile = result.profile_result;
  const warnings = [
    ...(profile.confidence_level === "low" || profile.confidence_level === "basic" ? ["Уверенность ограничена коротким профилем или неизвестными полями."] : []),
    ...(profile.pti_band === "high" || profile.pti_band === "very_high" ? ["Расчётная долговая нагрузка повышена."] : []),
    ...(profile.profile_bands?.credit_history_band === "unknown" ? ["Кредитная история не указана."] : []),
    "Данные БКИ и документы банка не используются.",
  ];
  return (
    <article className="profile-summary-card">
      <span className="section-kicker light">Предварительный профиль</span>
      <h3>Оценка по введённым данным</h3>
      <div className="profile-summary-grid">
        <div><span>Долговая нагрузка</span><strong>{profile.pti_value === null ? "—" : formatPercent(profile.pti_value, 0)}</strong><small>{bandLabels[profile.pti_band] ?? profile.pti_band}</small></div>
        <div><span>Платёж</span><strong>{profile.estimated_monthly_payment === null ? "—" : `${money.format(Math.round(profile.estimated_monthly_payment))} ₽`}</strong><small>ориентировочно</small></div>
        <div><span>Комфорт платежа</span><strong>{bandLabels[profile.affordability_band] ?? profile.affordability_band}</strong><small>по указанным данным</small></div>
        <div><span>Уверенность</span><strong>{confidenceLabels[profile.confidence_level] ?? profile.confidence_level}</strong><small>покрытие {formatPercent(profile.data_coverage, 0)}</small></div>
      </div>
      <p className="eligible-count">Совместимых предложений: <strong>{result.offers.length}</strong></p>
      {warnings.map((warning) => <p className="profile-warning" key={warning}><AlertTriangle size={14} aria-hidden="true" />{warning}</p>)}
      <p className="profile-final-note">Финальное решение принимает банк.</p>
    </article>
  );
}

function OfferCard({ offer, clicking, onOpen, recommended = false, payment }: { offer: RankedOffer; clicking: boolean; onOpen: () => void; recommended?: boolean; payment: number | null }) {
  return (
    <article className={`offer-card public-offer-card ${recommended ? "is-recommended" : ""}`} id={recommended ? "recommended-offer" : undefined}>
      <div className="offer-rank">{recommended ? <><Star size={14} /> Рекомендуемое предложение</> : `Вариант ${offer.rank}`}</div>
      <div className="offer-card-copy">
        <div className="offer-brand-line"><span className="offer-initials">{offer.advertiser_name.slice(0, 2).toUpperCase()}</span><span>{offer.advertiser_name}</span>{offer.is_demo ? <b>Демо-предложение</b> : null}</div>
        <h3>{offer.product_name}</h3>
        <p>{productLabels[offer.product_type] ?? offer.product_type}</p>
        {offer.main_benefit ? <strong className="offer-main-benefit">{offer.main_benefit}</strong> : null}
        {payment !== null ? <div className="offer-payment"><span>Ориентир платежа</span><strong>{money.format(Math.round(payment))} ₽/мес.</strong></div> : null}
        <div className="offer-range">{money.format(offer.min_amount)}–{money.format(offer.max_amount)} ₽ · {offer.min_term_months}–{offer.max_term_months} мес.</div>
        <small>Уверенность: {confidenceLabels[offer.confidence_level] ?? offer.confidence_level}</small>
        {offer.positive_reasons.map((reason) => <em key={reason}><CheckCircle2 size={13} aria-hidden="true" />{reason}</em>)}
        {offer.warnings.map((warning) => <i key={warning}><AlertTriangle size={13} aria-hidden="true" />{warning}</i>)}
        {offer.full_cost_range_text ? <div className="offer-full-cost">{offer.full_cost_range_text}</div> : null}
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
      <h3>Понятный результат без лишних данных</h3>
      <ul>
        <li>Ориентировочный платёж</li>
        <li>Долговую нагрузку</li>
        <li>Подходящие предложения</li>
        <li>Объяснение, почему они показаны</li>
      </ul>
      <small>Финальное решение принимает банк.</small>
    </div>
  );
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
