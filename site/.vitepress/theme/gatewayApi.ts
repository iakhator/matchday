// Thin wrapper around the gateway's own /account/keys endpoints (see
// app/api/v1/routes/account.py). Defaults to the local dev gateway so
// `npm run dev` here works against a `docker compose up` gateway with no
// extra config - override via VITE_GATEWAY_API_BASE_URL for anything else.
const BASE_URL = import.meta.env.VITE_GATEWAY_API_BASE_URL || "http://localhost:8010";

export interface ApiKeySummary {
  id: string;
  name: string;
  key_prefix: string;
  requests_per_minute: number;
  created_at: string | null;
  last_used_at: string | null;
}

export interface ApiKeyCreated extends ApiKeySummary {
  secret: string;
}

class GatewayApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function request<T>(
  path: string,
  token: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${BASE_URL}/api/v1${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new GatewayApiError(
      body.detail || `Request failed (${res.status})`,
      res.status,
    );
  }

  return res.json();
}

export async function listKeys(token: string): Promise<ApiKeySummary[]> {
  const data = await request<{ items: ApiKeySummary[] }>("/account/keys", token);
  return data.items;
}

export async function createKey(token: string, name: string): Promise<ApiKeyCreated> {
  return request<ApiKeyCreated>("/account/keys", token, {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function revokeKey(token: string, id: string): Promise<void> {
  await request<ApiKeySummary>(`/account/keys/${id}`, token, { method: "DELETE" });
}

export async function rotateKey(token: string, id: string): Promise<ApiKeyCreated> {
  return request<ApiKeyCreated>(`/account/keys/${id}/rotate`, token, {
    method: "POST",
  });
}
