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
  bankId: string; productName: string; productType: string; isActive: boolean;
  priority: string; minAmount: string; maxAmount: string;
  minTermMonths: string; maxTermMonths: string; ageBands: string;
  minIncomeBand: string; regions: string; employmentTypes: string;
  creditHistoryBands: string; maxPtiBand: string; riskBandPolicy: string;
  advertiserName: string; adLabelText: string; erid: string;
  legalDisclaimer: string; partnerId: string; affiliateTemplateKey: string;
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
          <span className="section-kicker">Offer catalog</span>
          <h2>Каталог без ручного редактирования YAML</h2>
          <p>
            Управляйте правилами, disclosure и статусом. URL, токены и partner secrets здесь
            не вводятся — разрешены только ссылки на переменные окружения.
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
              <span className="section-kicker">{editingId === null ? "Create" : `Edit #${editingId}`}</span>
              <h3>{editingId === null ? "Новый оффер" : "Редактирование оффера"}</h3>
            </div>
          </div>

          <div className="operator-form-grid">
            <Field label="bank_id" value={draft.bankId} onChange={(value) => update("bankId", value)} required />
            <Field label="Название продукта" value={draft.productName} onChange={(value) => update("productName", value)} required />
            <Field label="Тип продукта" value={draft.productType} onChange={(value) => update("productType", value)} required />
            <SelectField label="Статус" value={draft.isActive ? "active" : "inactive"} onChange={(value) => update("isActive", value === "active")} options={["active", "inactive"]} />
            <Field label="Приоритет" type="number" value={draft.priority} onChange={(value) => update("priority", value)} />
            <Field label="Минимальная сумма" type="number" value={draft.minAmount} onChange={(value) => update("minAmount", value)} />
            <Field label="Максимальная сумма" type="number" value={draft.maxAmount} onChange={(value) => update("maxAmount", value)} />
            <Field label="Минимальный срок, мес." type="number" value={draft.minTermMonths} onChange={(value) => update("minTermMonths", value)} />
            <Field label="Максимальный срок, мес." type="number" value={draft.maxTermMonths} onChange={(value) => update("maxTermMonths", value)} />
            <Field label="Возрастные диапазоны" value={draft.ageBands} onChange={(value) => update("ageBands", value)} help="Через запятую: 22_30, 31_45" />
            <SelectField label="Минимальный доход" value={draft.minIncomeBand} onChange={(value) => update("minIncomeBand", value)} options={["lt_50k", "50k_100k", "100k_150k", "150k_250k", "gt_250k", "unknown"]} />
            <Field label="Регионы" value={draft.regions} onChange={(value) => update("regions", value)} help="Пусто — без регионального ограничения" />
            <Field label="Типы занятости" value={draft.employmentTypes} onChange={(value) => update("employmentTypes", value)} />
            <Field label="Кредитная история" value={draft.creditHistoryBands} onChange={(value) => update("creditHistoryBands", value)} />
            <SelectField label="Максимальный PTI" value={draft.maxPtiBand} onChange={(value) => update("maxPtiBand", value)} options={["low", "moderate", "high", "very_high", "unknown"]} />
            <Field label="Risk policy" value={draft.riskBandPolicy} onChange={(value) => update("riskBandPolicy", value)} />
            <Field label="Рекламодатель" value={draft.advertiserName} onChange={(value) => update("advertiserName", value)} required />
            <Field label="Маркировка рекламы" value={draft.adLabelText} onChange={(value) => update("adLabelText", value)} required />
            <Field label="ERID" value={draft.erid} onChange={(value) => update("erid", value)} />
            <Field label="partner_id" value={draft.partnerId} onChange={(value) => update("partnerId", value)} required />
            <Field label="Affiliate template env key" value={draft.affiliateTemplateKey} onChange={(value) => update("affiliateTemplateKey", value)} help="Например: ALFA_CREDIT_AFFILIATE_TEMPLATE. Не вставляйте URL или token." />
            <SelectField label="Тип комиссии" value={draft.commissionType} onChange={(value) => update("commissionType", value)} options={["none", "fixed", "percent"]} />
            <Field label="Комиссия (внутреннее поле)" type="number" value={draft.commissionAmount} onChange={(value) => update("commissionAmount", value)} />
            <Field label="Действует до" type="datetime-local" value={draft.expiresAt} onChange={(value) => update("expiresAt", value)} />
          </div>
          <label className="operator-textarea-field">
            <span>Юридический disclaimer</span>
            <textarea value={draft.legalDisclaimer} onChange={(event) => update("legalDisclaimer", event.target.value)} rows={3} required />
          </label>

          {preview ? (
            <div className={`validation-preview ${preview.valid ? "valid" : "invalid"}`}>
              {preview.valid ? <CheckCircle2 size={18} /> : <XCircle size={18} />}
              <div>
                <strong>{preview.valid ? "Проверка пройдена" : "Найдены ошибки"}</strong>
                {[...preview.errors, ...preview.warnings].map((item) => <span key={item}>{item}</span>)}
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
                      <span className={offer.is_active ? "status-active" : "status-inactive"}>{offer.is_active ? "active" : "inactive"}</span>
                      <span className={offer.validation_status === "valid" ? "status-valid" : "status-invalid"}>{offer.validation_status}</span>
                    </div>
                    <small>{offer.bank_id} · {offer.product_type} · priority {offer.priority}</small>
                    <p>{offer.min_amount.toLocaleString("ru-RU")}–{offer.max_amount.toLocaleString("ru-RU")} ₽ · {offer.min_term_months}–{offer.max_term_months} мес.</p>
                    <div className="quality-flags">
                      {offer.quality_flags.length ? offer.quality_flags.map((flag) => <i key={flag}>{flag}</i>) : <i className="ok">без quality flags</i>}
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
