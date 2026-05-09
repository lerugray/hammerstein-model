import type { CallsResponse, Status, Call } from "./types";

async function jget<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} → ${r.status}`);
  return r.json() as Promise<T>;
}

export const api = {
  status: () => jget<Status>("/api/status"),
  calls: (limit = 100, offset = 0) =>
    jget<CallsResponse>(`/api/calls?limit=${limit}&offset=${offset}`),
  call: (timestamp: string) => jget<Call>(`/api/calls/${encodeURIComponent(timestamp)}`),
  setConclusionChanged: async (timestamp: string, value: boolean | null) => {
    const r = await fetch("/api/conclusion-changed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ timestamp, conclusion_changed: value }),
    });
    if (!r.ok) throw new Error(`POST conclusion-changed → ${r.status}`);
    return r.json();
  },
};
