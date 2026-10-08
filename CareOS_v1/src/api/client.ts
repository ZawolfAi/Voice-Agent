const API_BASE = import.meta.env.VITE_API_URL || "/api/v1";

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

export async function request<T>(path: string, options: RequestInit = {}, tokenKey = "careos-access-token"): Promise<T> {
  const token = localStorage.getItem(tokenKey);
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    if (response.status === 401) clearSession();
    throw new ApiError(response.status, body.detail || "Request failed");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function portalRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  return request<T>(path, options, "careos-portal-token");
}

export function clearSession(): void {
  localStorage.removeItem("careos-access-token");
  localStorage.removeItem("careos-portal-token");
  localStorage.removeItem("careos-demo-mode");
  localStorage.removeItem("careos-demo-user");
}