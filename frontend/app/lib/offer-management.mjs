export const initialOfferDraft = Object.freeze({
  providerId: "demo",
  providerOfferId: "",
  bankId: "",
  productName: "",
  productType: "cash",
  isActive: true,
  priority: "50",
  minAmount: "50000",
  maxAmount: "500000",
  minTermMonths: "6",
  maxTermMonths: "60",
  annualRateMin: "",
  annualRateMax: "",
  feeDisclosure: "",
  insuranceDisclosure: "",
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
  fullCostRangeText: "",
  compensationDisclosure: "Сервис может получить вознаграждение за переход.",
  partnerTermsUrl: "",
  mainBenefit: "",
  displayWarnings: "",
  ctaText: "Посмотреть условия",
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
  const rateMin = draft.annualRateMin === "" ? null : Number(draft.annualRateMin);
  const rateMax = draft.annualRateMax === "" ? null : Number(draft.annualRateMax);
  if (!SAFE_ID.test(draft.providerId)) errors.push("Укажите корректный provider_id.");
  if (!SAFE_ID.test(draft.bankId)) errors.push("Укажите корректный bank_id.");
  if (!draft.productName.trim()) errors.push("Укажите название продукта.");
  if (!SAFE_ID.test(draft.productType)) errors.push("Укажите корректный тип продукта.");
  if (!(minAmount > 0) || maxAmount < minAmount) errors.push("Проверьте диапазон суммы.");
  if (!(minTerm >= 3) || maxTerm < minTerm) errors.push("Проверьте диапазон срока.");
  if ((rateMin === null) !== (rateMax === null) || (rateMin !== null && (!(rateMin >= 0) || rateMax < rateMin || rateMax > 100))) errors.push("Проверьте диапазон ставки.");
  if (rateMin !== null && !draft.fullCostRangeText.trim()) errors.push("Для ставки нужен диапазон полной стоимости кредита.");
  if (!splitList(draft.ageBands).length) errors.push("Выберите возрастные диапазоны.");
  if (!splitList(draft.employmentTypes).length) errors.push("Укажите типы занятости.");
  if (!splitList(draft.creditHistoryBands).length) errors.push("Укажите правила кредитной истории.");
  if (!splitList(draft.riskBandPolicy).length) errors.push("Укажите risk policy.");
  if (draft.isActive && (!draft.advertiserName.trim() || !draft.adLabelText.trim() || !draft.legalDisclaimer.trim())) {
    errors.push("Активному офферу нужны рекламодатель и disclosure.");
  }
  if (draft.isActive && !draft.compensationDisclosure.trim()) {
    errors.push("Добавьте информацию о возможном вознаграждении сервиса.");
  }
  if (/ставк|процент|\d(?:[\s.,]\d)?\s*%/i.test(`${draft.productName} ${draft.mainBenefit} ${draft.adLabelText}`) && !draft.fullCostRangeText.trim()) {
    errors.push("При упоминании ставки укажите диапазон полной стоимости кредита.");
  }
  if (!SAFE_ID.test(draft.partnerId)) errors.push("Укажите корректный partner_id.");
  if (draft.partnerId !== "demo" && draft.isActive && !draft.affiliateTemplateKey.trim()) {
    errors.push("Активному real-partner нужен env-key шаблона.");
  }
  if (draft.partnerId !== "demo" && draft.isActive && !draft.partnerTermsUrl.trim()) {
    errors.push("Для активного партнёра нужна публичная ссылка на условия.");
  }
  if (draft.affiliateTemplateKey && !ENV_KEY.test(draft.affiliateTemplateKey)) {
    errors.push("Шаблон задаётся только uppercase env-key reference.");
  }
  if (draft.partnerTermsUrl && !/^https:\/\/[^?#]+$/i.test(draft.partnerTermsUrl)) {
    errors.push("Ссылка на условия должна использовать HTTPS и не содержать параметров.");
  }
  if ([draft.productName, draft.advertiserName, draft.adLabelText, draft.legalDisclaimer, draft.mainBenefit, draft.partnerTermsUrl].some((value) => RAW_SECRET_URL.test(value))) {
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
    provider_id: draft.providerId.trim(),
    provider_offer_id: draft.providerOfferId.trim() || null,
    bank_id: draft.bankId.trim(),
    product_name: draft.productName.trim(),
    product_type: draft.productType.trim(),
    is_active: Boolean(draft.isActive),
    priority: Number(draft.priority),
    min_amount: Number(draft.minAmount),
    max_amount: Number(draft.maxAmount),
    min_term_months: Number(draft.minTermMonths),
    max_term_months: Number(draft.maxTermMonths),
    annual_rate_min: draft.annualRateMin === "" ? null : Number(draft.annualRateMin),
    annual_rate_max: draft.annualRateMax === "" ? null : Number(draft.annualRateMax),
    fee_disclosure: draft.feeDisclosure.trim() || null,
    insurance_disclosure: draft.insuranceDisclosure.trim() || null,
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
    full_cost_range_text: draft.fullCostRangeText.trim() || null,
    compensation_disclosure: draft.compensationDisclosure.trim(),
    partner_terms_url: draft.partnerTermsUrl.trim() || null,
    main_benefit: draft.mainBenefit.trim() || null,
    display_warnings: splitList(draft.displayWarnings),
    cta_text: draft.ctaText,
    partner_id: draft.partnerId.trim(),
    affiliate_url_template_key: draft.affiliateTemplateKey.trim() || null,
    commission_type: draft.commissionType,
    commission_amount: draft.commissionAmount === "" ? null : Number(draft.commissionAmount),
    expires_at: draft.expiresAt || null,
  };
}

export function offerToDraft(offer) {
  return {
    providerId: offer.provider_id,
    providerOfferId: offer.provider_offer_id ?? "",
    bankId: offer.bank_id,
    productName: offer.product_name,
    productType: offer.product_type,
    isActive: offer.is_active,
    priority: String(offer.priority),
    minAmount: String(offer.min_amount),
    maxAmount: String(offer.max_amount),
    minTermMonths: String(offer.min_term_months),
    maxTermMonths: String(offer.max_term_months),
    annualRateMin: offer.annual_rate_min === null ? "" : String(offer.annual_rate_min),
    annualRateMax: offer.annual_rate_max === null ? "" : String(offer.annual_rate_max),
    feeDisclosure: offer.fee_disclosure ?? "",
    insuranceDisclosure: offer.insurance_disclosure ?? "",
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
    fullCostRangeText: offer.full_cost_range_text ?? "",
    compensationDisclosure: offer.compensation_disclosure,
    partnerTermsUrl: offer.partner_terms_url ?? "",
    mainBenefit: offer.main_benefit ?? "",
    displayWarnings: offer.display_warnings.join(", "),
    ctaText: offer.cta_text,
    partnerId: offer.partner_id,
    affiliateTemplateKey: offer.affiliate_url_template_key ?? "",
    commissionType: offer.commission_type,
    commissionAmount: offer.commission_amount === null ? "" : String(offer.commission_amount),
    expiresAt: offer.expires_at ? offer.expires_at.slice(0, 16) : "",
  };
}
