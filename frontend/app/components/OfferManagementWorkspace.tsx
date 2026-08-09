"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, LoaderCircle, Pencil, Plus, Search, XCircle } from "lucide-react";
import {
  apiFetch,
  type OfferValidationResult,
  type OperatorOffer,
  type OperatorOfferList,
} from "../lib/api";
import {
  buildOfferPayload,
  initialOfferDraft,
  offerToDraft,
  validateOfferDraft,
} from "../lib/offer-management.mjs";

type Filter = "all" | "active" | "inactive";
interface OfferDraft {
  providerId: string; providerOfferId: string;
  bankId: string; productName: string; productType: string; isActive: boolean;
  priority: string; minAmount: string; maxAmount: string;
  minTermMonths: string; maxTermMonths: string; ageBands: string;
  annualRateMin: string; annualRateMax: string; feeDisclosure: string; insuranceDisclosure: string;
  minIncomeBand: string; regions: string; employmentTypes: string;
  creditHistoryBands: string; maxPtiBand: string; riskBandPolicy: string;
  advertiserName: string; adLabelText: string; erid: string;
  legalDisclaimer: string; fullCostRangeText: string; compensationDisclosure: string;
  partnerTermsUrl: string; mainBenefit: string; displayWarnings: string; ctaText: string;
  partnerId: string; affiliateTemplateKey: string;
  commissionType: string; commissionAmount: string; expiresAt: string;
}

export function OfferManagementWorkspace() {
  const [offers, setOffers] = useState<OperatorOffer[]>([]);
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState<OfferDraft>({ ...initialOfferDraft });
  const [preview, setPreview] = useState<OfferValidationResult | null>(null);

  const loadOffers = useCallback(async () => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams();
    if (filter !== "all") params.set("active", String(filter === "active"));
    if (search.trim()) params.set("search", search.trim());
    try {
      const result = await apiFetch<OperatorOfferList>(
        `v1/operator/offers${params.size ? `?${params}` : ""}`,
      );
      setOffers(result.items);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить офферы.");
    } finally {
      setLoading(false);
    }
  }, [filter, search]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadOffers(), 0);
    return () => window.clearTimeout(timer);
  }, [loadOffers]);

  function update<K extends keyof OfferDraft>(name: K, value: OfferDraft[K]) {
    setDraft((current) => ({ ...current, [name]: value }));
    setPreview(null);
  }

  function resetEditor() {
    setEditingId(null);
    setDraft({ ...initialOfferDraft });
    setPreview(null);
    setError(null);
  }

  function editOffer(offer: OperatorOffer) {
    setEditingId(offer.id);
    setDraft(offerToDraft(offer));
    setPreview(null);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function validatePreview() {
    const errors = validateOfferDraft(draft);
    if (errors.length) {
      setPreview({ valid: false, errors, warnings: [] });
      return;
    }
    if (editingId === null) {
      setPreview({
        valid: true,
        errors: [],
        warnings: ["Локальная проверка пройдена. Сервер повторит её при создании."],
      });
      return;
    }
    try {
      const result = await apiFetch<OfferValidationResult>(
        `v1/operator/offers/${editingId}/validate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(buildOfferPayload(draft)),
        },
      );
      setPreview(result);
    } catch (reason) {
      setPreview({
        valid: false,
        errors: [reason instanceof Error ? reason.message : "Серверная проверка недоступна."],
        warnings: [],
      });
    }
  }

  async function saveOffer(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const errors = validateOfferDraft(draft);
    if (errors.length) {
      setPreview({ valid: false, errors, warnings: [] });
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const path = editingId === null ? "v1/operator/offers" : `v1/operator/offers/${editingId}`;
      await apiFetch<OperatorOffer>(path, {
        method: editingId === null ? "POST" : "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildOfferPayload(draft)),
      });
      resetEditor();
      await loadOffers();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сохранить оффер.");
    } finally {
      setSaving(false);
    }
  }

  async function deactivateOffer(offer: OperatorOffer) {
    if (!window.confirm(`Деактивировать «${offer.product_name}»?`)) return;
    setError(null);
    try {
      await apiFetch<OperatorOffer>(`v1/operator/offers/${offer.id}/deactivate`, {
        method: "POST",
      });
      if (editingId === offer.id) resetEditor();
      await loadOffers();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось деактивировать оффер.");
    }
  }

  return (
    <div className="offer-management-stack">
      <section className="offer-management-intro">
        <div>
          <span className="section-kicker">Управление предложениями</span>
          <h2>Каталог партнёрских предложений</h2>
          <p>
            Настраивайте условия, отображение, маркировку и отслеживание без изменения
            конфигурационных файлов. Секретные значения здесь не вводятся.
          </p>
        </div>
        <button className="button button-dark" type="button" onClick={resetEditor}>
          <Plus size={17} /> Создать оффер
        </button>
      </section>

      {error ? <div className="commercial-state error"><AlertTriangle size={17} /> {error}</div> : null}

      <section className="operator-offer-layout">
        <form className="operator-offer-form" onSubmit={saveOffer} noValidate>
          <div className="panel-heading">
            <div>
              <span className="section-kicker">{editingId === null ? "Создание" : `Предложение №${editingId}`}</span>
              <h3>{editingId === null ? "Новый оффер" : "Редактирование оффера"}</h3>
            </div>
          </div>

          <section className="operator-form-section">
            <h4>1. Основное</h4>
            <div className="operator-form-grid">
            <Field label="Источник каталога" value={draft.providerId} onChange={(value) => update("providerId", value)} required />
            <Field label="ID продукта у источника" value={draft.providerOfferId} onChange={(value) => update("providerOfferId", value)} help="Стабильный ID без URL и секретов" />
            <Field label="Партнёр или банк (идентификатор)" value={draft.bankId} onChange={(value) => update("bankId", value)} required />
            <Field label="Название предложения" value={draft.productName} onChange={(value) => update("productName", value)} required />
            <Field label="Тип продукта" value={draft.productType} onChange={(value) => update("productType", value)} required />
            <SelectField label="Статус" value={draft.isActive ? "Активно" : "Неактивно"} onChange={(value) => update("isActive", value === "Активно")} options={["Активно", "Неактивно"]} />
            <Field label="Порядок показа" type="number" value={draft.priority} onChange={(value) => update("priority", value)} />
            </div>
          </section>

          <section className="operator-form-section">
            <h4>2. Условия</h4>
            <div className="operator-form-grid">
            <Field label="Минимальная сумма" type="number" value={draft.minAmount} onChange={(value) => update("minAmount", value)} />
            <Field label="Максимальная сумма" type="number" value={draft.maxAmount} onChange={(value) => update("maxAmount", value)} />
            <Field label="Минимальный срок, мес." type="number" value={draft.minTermMonths} onChange={(value) => update("minTermMonths", value)} />
            <Field label="Максимальный срок, мес." type="number" value={draft.maxTermMonths} onChange={(value) => update("maxTermMonths", value)} />
            <Field label="Ставка от, %" type="number" value={draft.annualRateMin} onChange={(value) => update("annualRateMin", value)} help="Только проверенный диапазон; требует текста ПСК" />
            <Field label="Ставка до, %" type="number" value={draft.annualRateMax} onChange={(value) => update("annualRateMax", value)} />
            <Field label="Комиссии продукта" value={draft.feeDisclosure} onChange={(value) => update("feeDisclosure", value)} />
            <Field label="Страхование" value={draft.insuranceDisclosure} onChange={(value) => update("insuranceDisclosure", value)} />
            <Field label="Возрастные диапазоны" value={draft.ageBands} onChange={(value) => update("ageBands", value)} help="Через запятую: 22_30, 31_45" />
            <SelectField label="Минимальный доход" value={draft.minIncomeBand} onChange={(value) => update("minIncomeBand", value)} options={["lt_50k", "50k_100k", "100k_150k", "150k_250k", "gt_250k", "unknown"]} />
            <Field label="Регионы" value={draft.regions} onChange={(value) => update("regions", value)} help="Пусто — без регионального ограничения" />
            <Field label="Типы занятости" value={draft.employmentTypes} onChange={(value) => update("employmentTypes", value)} />
            <Field label="Кредитная история" value={draft.creditHistoryBands} onChange={(value) => update("creditHistoryBands", value)} />
            <SelectField label="Максимальная долговая нагрузка" value={draft.maxPtiBand} onChange={(value) => update("maxPtiBand", value)} options={["low", "moderate", "high", "very_high", "unknown"]} />
            <Field label="Допустимые категории оценки" value={draft.riskBandPolicy} onChange={(value) => update("riskBandPolicy", value)} />
            </div>
          </section>

          <section className="operator-form-section">
            <h4>3. Отображение и маркировка</h4>
            <div className="operator-form-grid">
            <Field label="Рекламодатель" value={draft.advertiserName} onChange={(value) => update("advertiserName", value)} required />
            <Field label="Маркировка рекламы" value={draft.adLabelText} onChange={(value) => update("adLabelText", value)} required />
            <Field label="ERID" value={draft.erid} onChange={(value) => update("erid", value)} />
            <Field label="Главное преимущество" value={draft.mainBenefit} onChange={(value) => update("mainBenefit", value)} />
            <Field label="Предупреждения для клиента" value={draft.displayWarnings} onChange={(value) => update("displayWarnings", value)} help="Несколько предупреждений — через запятую" />
            <SelectField label="Текст кнопки" value={draft.ctaText} onChange={(value) => update("ctaText", value)} options={["Посмотреть условия", "Перейти к предложению", "Продолжить у партнёра"]} />
            <Field label="Диапазон полной стоимости" value={draft.fullCostRangeText} onChange={(value) => update("fullCostRangeText", value)} help="Обязательно, если в тексте предложения указана ставка" />
            <Field label="Действует до" type="datetime-local" value={draft.expiresAt} onChange={(value) => update("expiresAt", value)} />
            </div>
            <label className="operator-textarea-field"><span>Юридический текст</span><textarea value={draft.legalDisclaimer} onChange={(event) => update("legalDisclaimer", event.target.value)} rows={3} required /></label>
            <label className="operator-textarea-field"><span>Информация о вознаграждении сервиса</span><textarea value={draft.compensationDisclosure} onChange={(event) => update("compensationDisclosure", event.target.value)} rows={2} required /></label>
          </section>

          <section className="operator-form-section">
            <h4>4. Отслеживание и партнёрская интеграция</h4>
            <div className="operator-form-grid">
            <Field label="Идентификатор партнёра" value={draft.partnerId} onChange={(value) => update("partnerId", value)} required />
            <Field label="Ключ шаблона перехода" value={draft.affiliateTemplateKey} onChange={(value) => update("affiliateTemplateKey", value)} help="Например: ALFA_CREDIT_AFFILIATE_TEMPLATE. Только имя переменной окружения, без URL и токенов." />
            <Field label="Публичная ссылка на условия партнёра" value={draft.partnerTermsUrl} onChange={(value) => update("partnerTermsUrl", value)} help="HTTPS без параметров отслеживания" />
            <SelectField label="Тип вознаграждения" value={draft.commissionType} onChange={(value) => update("commissionType", value)} options={["none", "fixed", "percent"]} />
            <Field label="Размер вознаграждения (внутреннее поле)" type="number" value={draft.commissionAmount} onChange={(value) => update("commissionAmount", value)} />
            </div>
          </section>

          {preview ? (
            <div className={`validation-preview ${preview.valid ? "valid" : "invalid"}`}>
              {preview.valid ? <CheckCircle2 size={18} /> : <XCircle size={18} />}
              <div>
                <strong>{preview.valid ? "Готово к публикации" : "Нужны исправления"}</strong>
                {[...preview.errors, ...preview.warnings].map((item) => <span key={item}>{validationLabel(item)}</span>)}
              </div>
            </div>
          ) : null}

          <div className="button-row">
            <button className="button button-secondary" type="button" onClick={() => void validatePreview()}>
              Предварительная проверка
            </button>
            <button className="button button-dark" type="submit" disabled={saving}>
              {saving ? <LoaderCircle className="spin" size={17} /> : null}
              {editingId === null ? "Создать" : "Сохранить изменения"}
            </button>
            {editingId !== null ? <button className="button button-ghost" type="button" onClick={resetEditor}>Отмена</button> : null}
          </div>
        </form>

        <section className="operator-offer-catalog">
          <div className="offer-catalog-toolbar">
            <label className="offer-search">
              <Search size={16} />
              <input aria-label="Поиск по банку или продукту" placeholder="Поиск по банку или продукту" value={search} onChange={(event) => setSearch(event.target.value)} />
            </label>
            <select aria-label="Фильтр активности" value={filter} onChange={(event) => setFilter(event.target.value as Filter)}>
              <option value="all">Все</option>
              <option value="active">Активные</option>
              <option value="inactive">Неактивные</option>
            </select>
          </div>

          {loading ? <div className="commercial-state"><LoaderCircle className="spin" /> Загружаем каталог…</div> : null}
          {!loading && !offers.length ? <div className="commercial-state">Офферы не найдены. Создайте первый или измените фильтр.</div> : null}
          {!loading && offers.length ? (
            <div className="operator-offer-table" aria-label="Офферы">
              {offers.map((offer) => (
                <article className="operator-offer-row" key={offer.id}>
                  <div>
                    <div className="operator-offer-title">
                      <strong>{offer.product_name}</strong>
                      <span className={offer.is_active ? "status-active" : "status-inactive"}>{offer.is_active ? "активно" : "неактивно"}</span>
                      <span className={offer.validation_status === "valid" ? "status-valid" : "status-invalid"}>{offer.validation_status === "valid" ? "готово" : "нужна проверка"}</span>
                    </div>
                    <small>{offer.bank_id} · {offer.product_type} · источник {offer.provider_id} · порядок {offer.priority}</small>
                    <p>{offer.min_amount.toLocaleString("ru-RU")}–{offer.max_amount.toLocaleString("ru-RU")} ₽ · {offer.min_term_months}–{offer.max_term_months} мес.</p>
                    {offer.annual_rate_min !== null ? <p>Ставка {offer.annual_rate_min}–{offer.annual_rate_max}% · расчёт по диапазону продукта</p> : null}
                    <div className="quality-flags">
                      {offer.quality_flags.length ? offer.quality_flags.map((flag) => <i key={flag}>{qualityFlagLabel(flag)}</i>) : <i className="ok">замечаний нет</i>}
                    </div>
                  </div>
                  <div className="operator-offer-actions">
                    <button type="button" onClick={() => editOffer(offer)}><Pencil size={15} /> Изменить</button>
                    {offer.is_active ? <button className="danger" type="button" onClick={() => void deactivateOffer(offer)}>Деактивировать</button> : null}
                  </div>
                </article>
              ))}
            </div>
          ) : null}
        </section>
      </section>
    </div>
  );
}

function Field({ label, value, onChange, type = "text", help, required = false }: { label: string; value: string; onChange: (value: string) => void; type?: string; help?: string; required?: boolean }) {
  return (
    <label className="operator-field">
      <span>{label}</span>
      <input type={type} value={value} onChange={(event) => onChange(event.target.value)} required={required} />
      {help ? <small>{help}</small> : null}
    </label>
  );
}

function SelectField({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: string[] }) {
  return (
    <label className="operator-field">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => <option value={option} key={option}>{option}</option>)}
      </select>
    </label>
  );
}

const readableFlags: Record<string, string> = {
  missing_disclosure: "Нет рекламной пометки или юридического текста",
  missing_advertiser_name: "Не указан рекламодатель",
  missing_compensation_disclosure: "Нет информации о вознаграждении сервиса",
  missing_full_cost_range: "Не указан диапазон полной стоимости",
  missing_partner_terms_url: "Нет ссылки на условия партнёра",
  missing_affiliate_template_key: "Нет отслеживаемого перехода",
  affiliate_template_env_missing: "Партнёрские данные не настроены",
  placeholder_affiliate_url: "Демо-ссылка",
  demo_only: "Демо-предложение",
  erid_not_configured: "ERID не настроен — проверьте перед публичным размещением",
  expired_config: "Срок действия истёк",
  zero_impressions: "Нет показов",
  impressions_without_clicks: "Есть показы, но нет переходов",
  eligibility_too_broad: "Слишком широкие условия",
  eligibility_too_narrow: "Слишком узкие условия",
};

function qualityFlagLabel(flag: string): string {
  return readableFlags[flag] ?? flag.replaceAll("_", " ");
}

function validationLabel(value: string): string {
  const validation: Record<string, string> = {
    erid_not_configured: "ERID не настроен — проверьте перед публичным размещением.",
    demo_only: "Демо-предложение.",
    demo_link: "Используется демо-ссылка.",
    affiliate_template_environment_missing: "Партнёрские данные не настроены.",
    affiliate_template_click_id_missing: "Шаблон перехода не поддерживает отслеживание.",
  };
  return validation[value] ?? value.replaceAll("_", " ");
}
