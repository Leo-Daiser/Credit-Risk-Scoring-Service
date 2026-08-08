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
  term_months: number;
  existing_monthly_payments_band: "zero" | "lt_10k" | "10k_30k" | "30k_60k" | "gt_60k" | "unknown";
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
}

export interface RankedOffer {
  offer_id: number;
  rank: number;
  bank_id: string;
  product_name: string;
  advertiser_name: string;
  final_score: number;
  score_breakdown: Record<string, number>;
  match_reasons: string[];
  warnings: string[];
  ad_disclosure: string;
  redirect_url: string;
}

export interface OfferMatchResult {
  profile_result: CreditProfileResult;
  offers: RankedOffer[];
  disclaimers: string[];
  ad_disclosure_required: boolean;
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
    let message = `API вернул ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) message = payload.detail;
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
