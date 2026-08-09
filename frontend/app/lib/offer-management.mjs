export const initialOfferDraft = Object.freeze({
  bankId: "",
  productName: "",
  productType: "cash",
  isActive: true,
  priority: "50",
  minAmount: "50000",
  maxAmount: "500000",
  minTermMonths: "6",
  maxTermMonths: "60",
  ageBands: "22_30, 31_45, 46_60",
  minIncomeBand: "50k_100k",
  regions: "",
  employmentTypes: "employee, self_employed",
  creditHistoryBands: "good, average, no_history",
  maxPtiBand: "high",
  riskBandPolicy: "low, medium, unknown",
  advertiserName: "",
  adLabelText: "Реклама. Условия предварительные.",
  erid: "",
  legalDisclaimer: "Финальное решение и индивидуальные условия определяет банк.",
  partnerId: "demo",
  affiliateTemplateKey: "",
  commissionType: "none",
  commissionAmount: "",
  expiresAt: "",
});

const ENV_KEY = /^[A-Z][A-Z0-9_]{2,127}$/;
const SAFE_ID = /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/;
const RAW_SECRET_URL = /https?:\/\/\S*(token|secret|api[_-]?key|password)=/i;

export function splitList(value) {
  return [...new Set(String(value).split(/[,;|]/).map((item) => item.trim()).filter(Boolean))];
}

export function validateOfferDraft(draft) {
  const errors = [];
  const minAmount = Number(draft.minAmount);
  const maxAmount = Number(draft.maxAmount);
  const minTerm = Number(draft.minTermMonths);
  const maxTerm = Number(draft.maxTermMonths);
  if (!SAFE_ID.test(draft.bankId)) errors.push("Укажите корректный bank_id.");
  if (!draft.productName.trim()) errors.push("Укажите название продукта.");
  if (!SAFE_ID.test(draft.productType)) errors.push("Укажите корректный тип продукта.");
  if (!(minAmount > 0) || maxAmount < minAmount) errors.push("Проверьте диапазон суммы.");
  if (!(minTerm >= 3) || maxTerm < minTerm) errors.push("Проверьте диапазон срока.");
  if (!splitList(draft.ageBands).length) errors.push("Выберите возрастные диапазоны.");
  if (!splitList(draft.employmentTypes).length) errors.push("Укажите типы занятости.");
  if (!splitList(draft.creditHistoryBands).length) errors.push("Укажите правила кредитной истории.");
  if (!splitList(draft.riskBandPolicy).length) errors.push("Укажите risk policy.");
  if (draft.isActive && (!draft.advertiserName.trim() || !draft.adLabelText.trim() || !draft.legalDisclaimer.trim())) {
    errors.push("Активному офферу нужны рекламодатель и disclosure.");
  }
  if (!SAFE_ID.test(draft.partnerId)) errors.push("Укажите корректный partner_id.");
  if (draft.partnerId !== "demo" && draft.isActive && !draft.affiliateTemplateKey.trim()) {
    errors.push("Активному real-partner нужен env-key шаблона.");
  }
  if (draft.affiliateTemplateKey && !ENV_KEY.test(draft.affiliateTemplateKey)) {
    errors.push("Шаблон задаётся только uppercase env-key reference.");
  }
  if ([draft.productName, draft.advertiserName, draft.adLabelText, draft.legalDisclaimer].some((value) => RAW_SECRET_URL.test(value))) {
    errors.push("URL с token/secret параметрами запрещён.");
  }
  const commission = draft.commissionAmount === "" ? null : Number(draft.commissionAmount);
  if (draft.commissionType === "none" && commission !== null && commission !== 0) {
    errors.push("Для commission_type=none сумма должна быть пустой.");
  }
  if (draft.commissionType !== "none" && !(commission > 0)) {
    errors.push("Укажите положительную комиссию для внутреннего учёта.");
  }
  return errors;
}

export function buildOfferPayload(draft) {
  return {
    bank_id: draft.bankId.trim(),
    product_name: draft.productName.trim(),
    product_type: draft.productType.trim(),
    is_active: Boolean(draft.isActive),
    priority: Number(draft.priority),
    min_amount: Number(draft.minAmount),
    max_amount: Number(draft.maxAmount),
    min_term_months: Number(draft.minTermMonths),
    max_term_months: Number(draft.maxTermMonths),
    allowed_age_bands: splitList(draft.ageBands),
    min_income_band: draft.minIncomeBand,
    allowed_regions: splitList(draft.regions),
    allowed_employment_types: splitList(draft.employmentTypes),
    allowed_credit_history_bands: splitList(draft.creditHistoryBands),
    max_pti_band: draft.maxPtiBand,
    risk_band_policy: splitList(draft.riskBandPolicy),
    advertiser_name: draft.advertiserName.trim(),
    ad_label_text: draft.adLabelText.trim(),
    erid: draft.erid.trim() || null,
    legal_disclaimer: draft.legalDisclaimer.trim(),
    partner_id: draft.partnerId.trim(),
    affiliate_url_template_key: draft.affiliateTemplateKey.trim() || null,
    commission_type: draft.commissionType,
    commission_amount: draft.commissionAmount === "" ? null : Number(draft.commissionAmount),
    expires_at: draft.expiresAt || null,
  };
}

export function offerToDraft(offer) {
  return {
    bankId: offer.bank_id,
    productName: offer.product_name,
    productType: offer.product_type,
    isActive: offer.is_active,
    priority: String(offer.priority),
    minAmount: String(offer.min_amount),
    maxAmount: String(offer.max_amount),
    minTermMonths: String(offer.min_term_months),
    maxTermMonths: String(offer.max_term_months),
    ageBands: offer.allowed_age_bands.join(", "),
    minIncomeBand: offer.min_income_band,
    regions: offer.allowed_regions.join(", "),
    employmentTypes: offer.allowed_employment_types.join(", "),
    creditHistoryBands: offer.allowed_credit_history_bands.join(", "),
    maxPtiBand: offer.max_pti_band,
    riskBandPolicy: offer.risk_band_policy.join(", "),
    advertiserName: offer.advertiser_name,
    adLabelText: offer.ad_label_text,
    erid: offer.erid ?? "",
    legalDisclaimer: offer.legal_disclaimer,
    partnerId: offer.partner_id,
    affiliateTemplateKey: offer.affiliate_url_template_key ?? "",
    commissionType: offer.commission_type,
    commissionAmount: offer.commission_amount === null ? "" : String(offer.commission_amount),
    expiresAt: offer.expires_at ? offer.expires_at.slice(0, 16) : "",
  };
}
