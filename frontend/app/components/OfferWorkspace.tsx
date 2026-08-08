"use client";

import { AlertTriangle, ArrowRight, BadgePercent, CheckCircle2, LoaderCircle, ShieldCheck } from "lucide-react";
import { useState } from "react";
import type { CreditProfileInput, OfferMatchResult, RankedOffer } from "../lib/api";
import { apiFetch, formatPercent } from "../lib/api";
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

export function OfferWorkspace() {
  const [profile, setProfile] = useState(initialProfile);
  const [termDraft, setTermDraft] = useState("24");
  const [result, setResult] = useState<OfferMatchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [clicking, setClicking] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const update = <K extends keyof CreditProfileInput>(key: K, value: CreditProfileInput[K]) => {
    setProfile((current) => ({ ...current, [key]: value }));
  };

  const submit = async () => {
    const term = Number(termDraft);
    if (!Number.isInteger(term) || term < 3 || term > 120) {
      setError("Срок должен быть целым числом от 3 до 120 месяцев.");
      return;
    }
    if (!profile.consent_to_process) {
      setError("Для серверного подбора необходимо согласие на обработку введённых диапазонов.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await apiFetch<OfferMatchResult>("v1/offers/match", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile: { ...profile, term_months: term }, limit: 5 }),
      });
      setProfile((current) => ({ ...current, term_months: term }));
      setResult(response);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Подбор не выполнен.");
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
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            profile_id: result.profile_result.anonymous_profile_id,
            idempotency_key: `${result.profile_result.anonymous_profile_id}-${offer.offer_id}`,
          }),
        },
      );
      window.location.assign(click.redirect_url);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Переход не выполнен.");
      setClicking(null);
    }
  };

  return (
    <div className="offers-page">
      <section className="offers-intro">
        <div>
          <span className="section-kicker">Короткий профиль без документов</span>
          <h2>Сначала допустимость. Затем рейтинг.</h2>
          <p>
            Укажите только диапазоны. Сервис оценит примерную нагрузку и покажет подходящие
            демонстрационные предложения. Паспорт, телефон, адрес и данные БКИ не нужны.
          </p>
        </div>
        <div className="privacy-chip"><ShieldCheck size={20} /> Точные суммы не сохраняются</div>
      </section>

      <section className="offers-layout">
        <article className="panel offer-profile-form">
          <div className="panel-heading"><div><span className="section-kicker">Privacy-light profile</span><h3>Параметры подбора</h3></div></div>
          <div className="offer-fields">
            <SelectField label="Возраст" value={profile.age_band} onChange={(value) => update("age_band", value as CreditProfileInput["age_band"])} options={[["18_21", "18–21"], ["22_30", "22–30"], ["31_45", "31–45"], ["46_60", "46–60"], ["60_plus", "Старше 60"]]} />
            <SelectField label="Доход в месяц" value={profile.income_band} onChange={(value) => update("income_band", value as CreditProfileInput["income_band"])} options={[["lt_50k", "До 50 тыс."], ["50k_100k", "50–100 тыс."], ["100k_150k", "100–150 тыс."], ["150k_250k", "150–250 тыс."], ["gt_250k", "Более 250 тыс."], ["unknown", "Не указывать"]]} />
            <SelectField label="Занятость" value={profile.employment_type} onChange={(value) => update("employment_type", value as CreditProfileInput["employment_type"])} options={[["employee", "По найму"], ["self_employed", "Самозанятый"], ["individual_entrepreneur", "ИП"], ["pensioner", "Пенсионер"], ["unofficial", "Неофициально"], ["unemployed", "Без работы"], ["unknown", "Не указывать"]]} />
            <SelectField label="Сумма кредита" value={profile.requested_amount_band} onChange={(value) => update("requested_amount_band", value as CreditProfileInput["requested_amount_band"])} options={[["lt_100k", "До 100 тыс."], ["100k_300k", "100–300 тыс."], ["300k_700k", "300–700 тыс."], ["700k_1_5m", "700 тыс.–1,5 млн"], ["gt_1_5m", "Более 1,5 млн"]]} />
            <label className="field-label" htmlFor="offer-term-months">Срок, месяцев<NumericInput id="offer-term-months" min={3} max={120} step={1} value={termDraft} onValueChange={setTermDraft} /></label>
            <SelectField label="Текущие платежи" value={profile.existing_monthly_payments_band} onChange={(value) => update("existing_monthly_payments_band", value as CreditProfileInput["existing_monthly_payments_band"])} options={[["zero", "Нет"], ["lt_10k", "До 10 тыс."], ["10k_30k", "10–30 тыс."], ["30k_60k", "30–60 тыс."], ["gt_60k", "Более 60 тыс."], ["unknown", "Не указывать"]]} />
            <SelectField label="Кредитная история" value={profile.credit_history_band} onChange={(value) => update("credit_history_band", value as CreditProfileInput["credit_history_band"])} options={[["good", "Хорошая"], ["average", "Средняя"], ["minor_overdues", "Небольшие просрочки"], ["serious_overdues", "Серьёзные просрочки"], ["no_history", "Нет истории"], ["unknown", "Не указывать"]]} />
            <SelectField label="Цель" value={profile.loan_purpose} onChange={(value) => update("loan_purpose", value as CreditProfileInput["loan_purpose"])} options={[["cash", "Наличные"], ["refinance", "Рефинансирование"], ["car", "Автомобиль"], ["repair", "Ремонт"], ["education", "Образование"], ["medical", "Лечение"], ["other", "Другое"]]} />
          </div>
          <label className="consent-row">
            <input type="checkbox" checked={profile.consent_to_process} onChange={(event) => update("consent_to_process", event.target.checked)} />
            <span>Согласен на обработку диапазонов для предварительного подбора. Это не кредитное решение.</span>
          </label>
          <label className="consent-row secondary-consent">
            <input type="checkbox" checked={profile.consent_to_ad_personalization} onChange={(event) => update("consent_to_ad_personalization", event.target.checked)} />
            <span>Разрешаю персонализацию рекламных предложений.</span>
          </label>
          {error ? <div className="form-error" role="alert"><AlertTriangle size={18} /> {error}</div> : null}
          <button className="button button-dark button-full" type="button" onClick={submit} disabled={loading}>
            {loading ? <LoaderCircle className="spin" size={18} /> : <BadgePercent size={18} />}
            {loading ? "Подбираем…" : "Получить предварительный профиль и предложения"}
          </button>
          <p className="model-disclaimer">
            Сервис не принимает кредитных решений. Финальное решение принимает банк;
            предложения могут быть рекламными.
          </p>
        </article>

        <aside className="offer-results">
          {result ? (
            <>
              <ProfileSummary result={result} />
              {result.offers.length ? result.offers.map((offer) => (
                <article className="offer-card" key={offer.offer_id}>
                  <div className="offer-rank">#{offer.rank}</div>
                  <div className="offer-card-copy"><span>{offer.ad_disclosure}</span><h3>{offer.product_name}</h3><p>{offer.advertiser_name}</p><small>Соответствие профилю: {formatPercent(offer.final_score, 0)}</small></div>
                  <button className="button button-dark" type="button" onClick={() => openOffer(offer)} disabled={clicking === offer.offer_id}>{clicking === offer.offer_id ? <LoaderCircle className="spin" size={17} /> : <ArrowRight size={17} />} Перейти</button>
                </article>
              )) : <div className="offer-empty"><AlertTriangle size={24} /><strong>Подходящих предложений нет</strong><span>Сервис консервативно исключил предложения, не прошедшие правила допустимости.</span></div>}
              <div className="ad-boundary">Сервис не принимает кредитных решений. Финальное решение принимает банк. Предложения могут быть рекламными; сервис может получить вознаграждение за переход.</div>
            </>
          ) : (
            <div className="offer-empty initial"><CheckCircle2 size={27} /><strong>Результат появится здесь</strong><span>Мы покажем примерный PTI, уровень уверенности и только допустимые предложения.</span></div>
          )}
        </aside>
      </section>
    </div>
  );
}

function SelectField({ label, value, options, onChange }: { label: string; value: string; options: string[][]; onChange: (value: string) => void }) {
  return <label className="field-label">{label}<select value={value} onChange={(event) => onChange(event.target.value)}>{options.map(([optionValue, text]) => <option value={optionValue} key={optionValue}>{text}</option>)}</select></label>;
}

function ProfileSummary({ result }: { result: OfferMatchResult }) {
  const profile = result.profile_result;
  return <article className="profile-summary-card"><span className="section-kicker light">Предварительный профиль</span><div className="profile-summary-grid"><div><span>Нагрузка PTI</span><strong>{profile.pti_value === null ? "—" : formatPercent(profile.pti_value, 0)}</strong><small>{profile.pti_band}</small></div><div><span>Платёж</span><strong>{profile.estimated_monthly_payment === null ? "—" : `${Math.round(profile.estimated_monthly_payment).toLocaleString("ru-RU")} ₽`}</strong><small>ориентировочно</small></div><div><span>Риск</span><strong>{profile.risk_score_available ? profile.risk_band : "Недоступен"}</strong><small>не вероятность одобрения</small></div><div><span>Уверенность</span><strong>{profile.confidence_level}</strong><small>по полноте данных</small></div></div>{profile.warnings.map((warning) => <p className="profile-warning" key={warning}>{warning}</p>)}</article>;
}
