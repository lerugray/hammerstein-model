export type Verdict = "CONTINUE" | "EXTEND" | "ABORT";
export type GateStatus = "ok" | "warn" | "abort" | "unknown";
export type CallKind = "audit" | "vision";

export interface Gate {
  name: string;
  value: number | null;
  threshold: number;
  status: GateStatus;
  detail: string;
}

export interface Status {
  verdict: Verdict;
  window_days: number;
  hp_calls_in_window: number;
  baseline_calls_in_window: number;
  hp_avg_cost: number | null;
  baseline_avg_cost: number | null;
  gates: Gate[];
  issues: string[];
  warnings: string[];
}

export interface Call {
  timestamp: string;
  kind: CallKind;
  label: string;
  query: string;
  response: string;
  tokens: number;
  cost_usd: number | null;
  latency_ms: number | null;
  wrapper_elapsed_ms: number | null;
  conclusion_changed: boolean | null;
  exit_code: number | null;
  template: string | null;
  new_query_corpus_ids: number[];
  matched_prior_corpus_ids: number[];
  injected_prior_count: number | null;
  model: string | null;
  state_dir: string | null;
  images: string[];
  xlsx: string[];
  image_count: number | null;
  xlsx_count: number | null;
}

export interface CallsResponse {
  total: number;
  limit: number;
  offset: number;
  rows: Call[];
}
