// Wargamer mode API client. Backed by /api/wargame/* in
// web/backend/wargame_api.py.

import type { OrdersData, TurnLogEntry } from "./content";

export interface Campaign {
  slug: string;
  name: string;
  started: string;
  spend: number;
  spend_budget: number;
  model: string;
  turn: number;
}

export type SourceKind = "rules" | "reference";

export interface Source {
  kind: SourceKind;
  name: string;
  size_bytes: number;
  tokens_est: number;
  source: string;
  has_digest?: boolean;
  digest_size_bytes?: number;
  digest_tokens_est?: number;
}

export interface UploadSourcesResponse {
  accepted: Source[];
  errors: { file: string; error: string }[];
  sources: Source[];
}

export interface CampaignDetail {
  campaign: Campaign;
  turn_log: TurnLogEntry[];
  last_orders: OrdersData | null;
}

export interface IssueResponse {
  orders: OrdersData;
  campaign: Campaign;
  turn_log_entry: TurnLogEntry;
  cost_usd: number | null;
  latency_ms: number | null;
}

async function jget<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} → ${r.status}`);
  return r.json() as Promise<T>;
}

async function jpost<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(`${url} → ${r.status} ${text}`);
  }
  return r.json() as Promise<T>;
}

export const wargameApi = {
  list: () => jget<Campaign[]>("/api/wargame/campaigns"),
  get: (slug: string) =>
    jget<CampaignDetail>(`/api/wargame/campaigns/${encodeURIComponent(slug)}`),
  create: (body: { name: string; mission_md: string; spend_budget?: number; model?: string }) =>
    jpost<CampaignDetail>("/api/wargame/campaigns", body),
  listSources: (slug: string) =>
    jget<Source[]>(`/api/wargame/campaigns/${encodeURIComponent(slug)}/sources`),
  uploadSources: async (slug: string, files: File[]): Promise<UploadSourcesResponse> => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    const r = await fetch(
      `/api/wargame/campaigns/${encodeURIComponent(slug)}/sources`,
      { method: "POST", body: fd },
    );
    if (!r.ok) {
      const text = await r.text().catch(() => "");
      throw new Error(`upload sources → ${r.status} ${text}`);
    }
    return r.json() as Promise<UploadSourcesResponse>;
  },
  deleteSource: async (
    slug: string,
    kind: SourceKind,
    name: string,
  ): Promise<{ sources: Source[] }> => {
    const r = await fetch(
      `/api/wargame/campaigns/${encodeURIComponent(slug)}/sources/${kind}/${encodeURIComponent(name)}`,
      { method: "DELETE" },
    );
    if (!r.ok) {
      const text = await r.text().catch(() => "");
      throw new Error(`delete source → ${r.status} ${text}`);
    }
    return r.json();
  },
  regenerateDigest: async (
    slug: string,
    name: string,
  ): Promise<{ sources: Source[] }> => {
    const r = await fetch(
      `/api/wargame/campaigns/${encodeURIComponent(slug)}/sources/rules/${encodeURIComponent(name)}/regenerate-digest`,
      { method: "POST" },
    );
    if (!r.ok) {
      const text = await r.text().catch(() => "");
      throw new Error(`regenerate digest → ${r.status} ${text}`);
    }
    return r.json();
  },
  referenceImageUrl: (slug: string, name: string): string =>
    `/api/wargame/campaigns/${encodeURIComponent(slug)}/reference/${encodeURIComponent(name)}`,
  issue: async (
    slug: string,
    status: string,
    images: File[],
    xlsx: File | null,
  ): Promise<IssueResponse> => {
    const fd = new FormData();
    fd.append("status", status);
    for (const img of images) fd.append("images", img);
    if (xlsx) fd.append("xlsx", xlsx);
    const r = await fetch(
      `/api/wargame/campaigns/${encodeURIComponent(slug)}/issue`,
      { method: "POST", body: fd },
    );
    if (!r.ok) {
      const text = await r.text().catch(() => "");
      throw new Error(`issue → ${r.status} ${text}`);
    }
    return r.json() as Promise<IssueResponse>;
  },
};
