export interface ModelInfo {
  model_version: string;
  model_type: string;
  created_at: string | null;
  feature_count: number;
  decision_threshold: number;
  risk_bands: Array<{ name: string; upper_bound: number | null }>;
  metrics: Record<string, number | null>;
  confidence_intervals: Record<string, { lower?: number; upper?: number }>;
  acceptance_status: string | null;
}

export interface HistoryItem {
  request_id: string;
  received_at: string;
  default_probability: number;
  decision: "approve" | "decline" | null;
  decision_threshold: number | null;
  risk_band: string;
  model_version: string;
}

export interface DashboardData {
  generated_at: string;
  model: ModelInfo;
  scoring: {
    total: number;
    last_24h: number;
    approval_rate: number | null;
    mean_default_probability: number | null;
    risk_bands: Record<string, number>;
  };
  batches: Record<"queued" | "running" | "completed" | "failed", number>;
  recent_decisions: HistoryItem[];
}

export interface FeatureSchema {
  model_version: string;
  feature_count: number;
  numeric_features: string[];
  categorical_features: string[];
  required_features: string[];
  min_feature_coverage: number;
}

export interface BatchJob {
  job_id: string;
  original_filename: string;
  input_format: "csv" | "parquet";
  id_column: string;
  file_size_bytes: number;
  status: "queued" | "running" | "completed" | "failed";
  rows_total: number | null;
  rows_processed: number;
  model_version: string | null;
  summary_json: Record<string, number | string> | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface ScoreResult {
  request_id: string;
  default_probability: number;
  decision: "approve" | "decline";
  decision_threshold: number;
  risk_band: string;
  reason_codes: Array<{
    code: string;
    feature: string;
    contribution: number;
    description: string;
  }>;
  model_version: string;
  missing_feature_count: number;
  input_quality: {
    supplied_feature_count: number;
    supplied_feature_coverage: number;
    missing_feature_count: number;
    out_of_range_features: string[];
    unseen_categorical_features: string[];
    warnings: string[];
  };
  latency_ms: number;
  logging_status: "persisted" | "disabled" | "failed";
}

export interface CreditProfileInput {
  age_band: "18_21" | "22_30" | "31_45" | "46_60" | "60_plus";
  region?: string;
  income_band: "lt_50k" | "50k_100k" | "100k_150k" | "150k_250k" | "gt_250k" | "unknown";
  employment_type: "employee" | "self_employed" | "individual_entrepreneur" | "pensioner" | "unofficial" | "unemployed" | "unknown";
  requested_amount_band: "lt_100k" | "100k_300k" | "300k_700k" | "700k_1_5m" | "gt_1_5m";
  requested_amount?: number;
  term_months: number;
  existing_monthly_payments_band: "zero" | "lt_10k" | "10k_30k" | "30k_60k" | "gt_60k" | "unknown";
  existing_monthly_payments?: number;
  credit_history_band: "good" | "average" | "minor_overdues" | "serious_overdues" | "no_history" | "unknown";
  loan_purpose: "cash" | "refinance" | "car" | "repair" | "education" | "medical" | "other";
  consent_to_process: boolean;
  consent_to_ad_personalization: boolean;
}

export interface CreditProfileResult {
  anonymous_profile_id: string;
  risk_band: string;
  risk_score_available: boolean;
  risk_score: number | null;
  affordability_band: string;
  estimated_monthly_payment: number | null;
  pti_value: number | null;
  pti_band: string;
  data_coverage: number;
  confidence_level: string;
  warnings: string[];
  disclaimers: string[];
  profile_bands: {
    age_band: string; region: string | null; income_band: string; employment_type: string;
    requested_amount_band: string; term_months: number; existing_monthly_payments_band: string;
    credit_history_band: string; loan_purpose: string;
  };
}

export interface RankedOffer {
  offer_id: number;
  rank: number;
  bank_id: string;
  product_name: string;
  product_type: string;
  advertiser_name: string;
  is_demo: boolean;
  min_amount: number;
  max_amount: number;
  min_term_months: number;
  max_term_months: number;
  positive_reasons: string[];
  warnings: string[];
  disclosure: string;
  ad_disclosure: string;
  confidence_level: string;
  main_benefit: string | null;
  full_cost_range_text: string | null;
  compensation_disclosure: string;
  legal_disclaimer: string;
  cta_text: string;
  redirect_url: string;
}

export interface OfferMatchResult {
  profile_result: CreditProfileResult;
  offers: RankedOffer[];
  disclaimers: string[];
  ad_disclosure_required: boolean;
  no_eligible_offers: boolean;
  user_explanation: string | null;
  suggestions: string[];
  why_not_reasons: string[];
}

export interface CommercialAnalytics {
  summary: {
    total_profile_scores: number; total_match_requests: number;
    total_offer_impressions: number; total_offer_clicks: number;
    ctr_overall: number; no_eligible_offers_rate: number;
    postback_conversion_rate: number; approval_rate: number; issued_rate: number;
    estimated_revenue: number; epc_proxy: number; recommended_offer_ctr: number;
    top_card_ctr: number; partner_redirect_failures: number;
  };
  offer_metrics: Array<{
    offer_id: number; product_name: string; impressions: number; clicks: number;
    ctr: number; approvals: number; issued: number; estimated_revenue: number; epc_proxy: number;
    expected_revenue_proxy: number; revenue_estimate_source: string;
  }>;
  experiment_metrics: Array<{
    variant: string; impressions: number; clicks: number; ctr: number;
    approvals: number; issued: number;
  }>;
  warnings: string[];
}

export interface OfferQualityReport {
  summary: {
    active_offers: number; inactive_offers: number;
    zero_impression_offers: number; impressions_without_clicks: number;
  };
  offers: Array<{
    offer_id: number; product_name: string; bank_id: string; status: string;
    quality_flags: string[]; impressions: number; clicks: number; ctr: number;
    postback_approval_rate: number; estimated_revenue: number; recommendation: string;
  }>;
}

export interface OperatorOffer {
  id: number;
  bank_id: string;
  product_name: string;
  product_type: string;
  is_active: boolean;
  priority: number;
  min_amount: number;
  max_amount: number;
  min_term_months: number;
  max_term_months: number;
  allowed_age_bands: string[];
  min_income_band: string;
  allowed_regions: string[];
  allowed_employment_types: string[];
  allowed_credit_history_bands: string[];
  max_pti_band: string;
  risk_band_policy: string[];
  advertiser_name: string;
  ad_label_text: string;
  erid: string | null;
  legal_disclaimer: string;
  full_cost_range_text: string | null;
  compensation_disclosure: string;
  partner_terms_url: string | null;
  main_benefit: string | null;
  display_warnings: string[];
  cta_text: string;
  partner_id: string;
  affiliate_url_template_key: string | null;
  commission_type: "none" | "fixed" | "percent";
  commission_amount: number | null;
  expires_at: string | null;
  validation_status: "valid" | "invalid";
  validation_errors: string[];
  quality_flags: string[];
  quality_recommendation: string;
}

export interface OperatorOfferList {
  items: OperatorOffer[];
  total: number;
}

export interface OfferValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

export interface SegmentOpportunityReport {
  opportunities: Array<{
    segment_key: string; segment_value: string; requests: number;
    eligible_offer_rate: number; click_rate: number; approval_rate: number | null;
    estimated_lost_clicks: number; recommendation: string;
  }>;
}

export interface EventDebugReport {
  events: Array<{
    event_type: string; click_id: string | null; offer_id: number | null;
    status: string | null; hmac_validation_status: string | null;
    experiment_variant: string; occurred_at: string;
  }>;
  raw_payloads_exposed: false;
}

const UNSAFE_PUBLIC_ERROR = /valueerror|traceback|sqlalchemy|postgres|select\s+.+\s+from|model[_\s-]bundle|ext_source|code_gender|amt_annuity/i;

function safePublicError(message: string, fallback: string): string {
  const normalized = message.trim();
  return normalized && normalized.length <= 240 && !UNSAFE_PUBLIC_ERROR.test(normalized)
    ? normalized
    : fallback;
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/backend/${path.replace(/^\//, "")}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let message = `Сервис временно недоступен (код ${response.status}).`;
    try {
      const payload = (await response.json()) as {
        detail?: string | { message?: string; errors?: string[] };
      };
      if (typeof payload.detail === "string") message = safePublicError(payload.detail, message);
      if (payload.detail && typeof payload.detail === "object") {
        const parts = [payload.detail.message, ...(payload.detail.errors ?? [])].filter(Boolean);
        if (parts.length) message = safePublicError(parts.join(" "), message);
      }
    } catch {
      // Keep the HTTP fallback when the response is not JSON.
    }
    throw new Error(message);
  }
  return (await response.json()) as T;
}

export function formatPercent(value: number | null, digits = 1): string {
  return value === null ? "—" : `${(value * 100).toFixed(digits)}%`;
}

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}
