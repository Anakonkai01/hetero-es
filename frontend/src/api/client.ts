const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

let demoToken = sessionStorage.getItem("heteroes.demo-token") ?? "";
let workspaceId = "";

export function setDemoToken(token: string) {
  demoToken = token;
  if (token) sessionStorage.setItem("heteroes.demo-token", token);
  else sessionStorage.removeItem("heteroes.demo-token");
}

export function setActiveWorkspace(id: string) {
  workspaceId = id;
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function isNotFoundError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (demoToken) headers.set("Authorization", `Bearer ${demoToken}`);
  if (workspaceId) headers.set("X-Workspace-Id", workspaceId);
  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });

  if (!response.ok) {
    const error = await response.json().catch(() => null) as { message?: string } | null;
    throw new ApiError(
      response.status,
      error?.message ?? `API request failed: ${response.status} ${response.statusText}`,
    );
  }

  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path);
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

export function apiDelete<T = void>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

/** True when the data source answered with a server error (as opposed to being unreachable). */
export function isServerError(error: unknown): boolean {
  return error instanceof ApiError && error.status >= 500;
}
