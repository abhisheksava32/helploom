/**
 * The only module that calls fetch for the REST API (docs/API.md).
 *
 * It adds the bearer token and the X-Organization-Id header, turns the error body
 * into a typed ApiError, and on a 401 with an expired token refreshes once and
 * retries. Session state stays in the auth context; the client reads it through
 * callbacks so it always sees the latest token.
 */

import { apiBase } from "@/lib/config";
import type { ApiErrorBody } from "@/lib/api/types";

export type HttpMethod = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
export type QueryValue = string | number | boolean | null | undefined;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** Field errors of a validation_error, for showing next to form inputs. */
  fieldErrors(): Record<string, string[]> {
    if (this.code !== "validation_error") return {};
    const result: Record<string, string[]> = {};
    for (const [field, value] of Object.entries(this.details)) {
      if (Array.isArray(value)) result[field] = value.map(String);
    }
    return result;
  }
}

export interface RequestOptions {
  method?: HttpMethod;
  /** JSON body. Ignored when formData is given. */
  body?: unknown;
  formData?: FormData;
  query?: Record<string, QueryValue | QueryValue[]>;
  signal?: AbortSignal;
  /** Send the bearer token and organisation header (default true). */
  auth?: boolean;
  /** Cookie endpoints (/auth/refresh/, /auth/logout/): send credentials and the CSRF guard header. */
  cookie?: boolean;
}

export interface ApiClientOptions {
  getAccessToken: () => string | null;
  getOrganizationId: () => string | null;
  /** Returns a fresh access token, or null when the session is gone. */
  refreshAccessToken: () => Promise<string | null>;
}

export interface ApiClient {
  request<T>(path: string, options?: RequestOptions): Promise<T>;
  get<T>(path: string, options?: Omit<RequestOptions, "method" | "body">): Promise<T>;
  post<T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">): Promise<T>;
  patch<T>(path: string, body: unknown, options?: Omit<RequestOptions, "method" | "body">): Promise<T>;
  delete(path: string, options?: Omit<RequestOptions, "method" | "body">): Promise<void>;
}

export function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(`${apiBase}${path.startsWith("/") ? path : `/${path}`}`);
  if (query) {
    for (const [key, raw] of Object.entries(query)) {
      const values = Array.isArray(raw) ? raw : [raw];
      for (const value of values) {
        if (value === undefined || value === null || value === "") continue;
        url.searchParams.append(key, String(value));
      }
    }
  }
  return url.toString();
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== "object" || value === null || !("error" in value)) return false;
  const error = (value as { error: unknown }).error;
  return typeof error === "object" && error !== null && "code" in error && "message" in error;
}

async function toApiError(response: Response): Promise<ApiError> {
  let parsed: unknown = null;
  try {
    parsed = await response.json();
  } catch {
    // Not JSON, for example a proxy error page.
  }
  if (isErrorBody(parsed)) {
    const { code, message, details } = parsed.error;
    return new ApiError(response.status, code, message, details ?? {});
  }
  return new ApiError(response.status, "server_error", "Something went wrong. Please try again.");
}

export function createApiClient(options: ApiClientOptions): ApiClient {
  async function send(path: string, request: RequestOptions, accessToken: string | null): Promise<Response> {
    const headers = new Headers({ Accept: "application/json" });
    let body: BodyInit | undefined;

    if (request.formData) {
      body = request.formData; // the browser sets the multipart boundary
    } else if (request.body !== undefined) {
      headers.set("Content-Type", "application/json");
      body = JSON.stringify(request.body);
    }
    if (request.auth !== false) {
      if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
      const organizationId = options.getOrganizationId();
      if (organizationId) headers.set("X-Organization-Id", organizationId);
    }
    if (request.cookie) headers.set("X-Requested-With", "XMLHttpRequest");

    try {
      return await fetch(buildUrl(path, request.query), {
        method: request.method ?? "GET",
        headers,
        body,
        signal: request.signal,
        credentials: request.cookie ? "include" : "omit",
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") throw error;
      throw new ApiError(0, "network_error", "Cannot reach the Helploom server. Check your connection.");
    }
  }

  async function request<T>(path: string, requestOptions: RequestOptions = {}): Promise<T> {
    let response = await send(path, requestOptions, options.getAccessToken());

    if (response.status === 401 && requestOptions.auth !== false && !requestOptions.cookie) {
      const error = await toApiError(response.clone());
      if (error.code === "token_not_valid" || error.code === "not_authenticated") {
        const fresh = await options.refreshAccessToken();
        if (fresh) response = await send(path, requestOptions, fresh);
      }
    }

    if (!response.ok) throw await toApiError(response);
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  type NoBody = Omit<RequestOptions, "method" | "body">;

  return {
    request,
    get: <T>(path: string, opts?: NoBody) => request<T>(path, { ...opts, method: "GET" }),
    post: <T>(path: string, body?: unknown, opts?: NoBody) =>
      request<T>(path, { ...opts, method: "POST", body }),
    patch: <T>(path: string, body: unknown, opts?: NoBody) =>
      request<T>(path, { ...opts, method: "PATCH", body }),
    delete: (path: string, opts?: NoBody) => request<void>(path, { ...opts, method: "DELETE" }),
  };
}
