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
