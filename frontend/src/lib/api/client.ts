/**
 * The only module that talks HTTP to the REST API (docs/API.md).
 *
 * It adds the bearer token and the X-Organization-Id header, turns the error body
 * into a typed ApiError, and on a 401 with an expired token refreshes once and
 * retries. Session state stays in lib/auth; the client reads it through callbacks so
 * it always sees the latest token.
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
  /** Cookie endpoints (/auth/refresh/, /auth/logout/, login, signup): send credentials and the CSRF guard header. */
  cookie?: boolean;
  /**
   * Bearer endpoints whose response sets a new refresh cookie (POST /auth/password/
   * rotates it). Without credentials the browser would drop that Set-Cookie and keep
   * the revoked one, ending the session at the next refresh.
   */
  withCredentials?: boolean;
}

export interface UploadOptions {
  query?: RequestOptions["query"];
  signal?: AbortSignal;
  /** Called with 0..1 as the request body is sent. */
  onProgress?: (fraction: number) => void;
}

export interface ApiClientOptions {
  getAccessToken: () => string | null;
  getOrganizationId: () => string | null;
  /** Returns a fresh access token, or null when the session is gone. */
  refreshAccessToken: () => Promise<string | null>;
}

type NoBody = Omit<RequestOptions, "method" | "body">;

export interface ApiClient {
  request<T>(path: string, options?: RequestOptions): Promise<T>;
  get<T>(path: string, options?: NoBody): Promise<T>;
  post<T>(path: string, body?: unknown, options?: NoBody): Promise<T>;
  patch<T>(path: string, body: unknown, options?: NoBody): Promise<T>;
  delete(path: string, options?: NoBody): Promise<void>;
  /** Multipart POST with upload progress (fetch cannot report request progress). */
  upload<T>(path: string, formData: FormData, options?: UploadOptions): Promise<T>;
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

function errorFromBody(status: number, parsed: unknown): ApiError {
  if (isErrorBody(parsed)) {
    const { code, message, details } = parsed.error;
    return new ApiError(status, code, message, details ?? {});
  }
  if (status === 429) return new ApiError(status, "throttled", "Too many requests. Please wait a moment.");
  return new ApiError(status, "server_error", "Something went wrong. Please try again.");
}

async function toApiError(response: Response): Promise<ApiError> {
  let parsed: unknown = null;
  try {
    parsed = await response.json();
  } catch {
    // Not JSON, for example a proxy error page.
  }
  return errorFromBody(response.status, parsed);
}

const networkError = () =>
  new ApiError(0, "network_error", "Cannot reach the Helploom server. Check your connection.");

function isExpiredToken(error: ApiError): boolean {
  return error.status === 401 && (error.code === "token_not_valid" || error.code === "not_authenticated");
}

export function createApiClient(options: ApiClientOptions): ApiClient {
  function authHeaders(accessToken: string | null): Record<string, string> {
    const headers: Record<string, string> = {};
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
    const organizationId = options.getOrganizationId();
    if (organizationId) headers["X-Organization-Id"] = organizationId;
    return headers;
  }

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
      for (const [name, value] of Object.entries(authHeaders(accessToken))) headers.set(name, value);
    }
    if (request.cookie) headers.set("X-Requested-With", "XMLHttpRequest");

    try {
      return await fetch(buildUrl(path, request.query), {
        method: request.method ?? "GET",
        headers,
        body,
        signal: request.signal,
        credentials: request.cookie || request.withCredentials ? "include" : "omit",
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") throw error;
      throw networkError();
    }
  }

  async function request<T>(path: string, requestOptions: RequestOptions = {}): Promise<T> {
    let response = await send(path, requestOptions, options.getAccessToken());

    if (response.status === 401 && requestOptions.auth !== false && !requestOptions.cookie) {
      const error = await toApiError(response.clone());
      if (isExpiredToken(error)) {
        const fresh = await options.refreshAccessToken();
        if (fresh) response = await send(path, requestOptions, fresh);
      }
    }

    if (!response.ok) throw await toApiError(response);
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  function sendUpload<T>(path: string, formData: FormData, accessToken: string | null, upload: UploadOptions) {
    return new Promise<T>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", buildUrl(path, upload.query));
      xhr.setRequestHeader("Accept", "application/json");
      for (const [name, value] of Object.entries(authHeaders(accessToken))) xhr.setRequestHeader(name, value);
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) upload.onProgress?.(event.loaded / event.total);
      };
      xhr.onload = () => {
        let parsed: unknown = null;
        try {
          parsed = xhr.responseText ? JSON.parse(xhr.responseText) : null;
        } catch {
          // Leave parsed as null; errorFromBody falls back to a generic message.
        }
        if (xhr.status >= 200 && xhr.status < 300) resolve(parsed as T);
        else reject(errorFromBody(xhr.status, parsed));
      };
      xhr.onerror = () => reject(networkError());
      xhr.onabort = () => reject(new DOMException("Upload cancelled.", "AbortError"));
      upload.signal?.addEventListener("abort", () => xhr.abort(), { once: true });
      xhr.send(formData);
    });
  }

  async function uploadWithRefresh<T>(path: string, formData: FormData, upload: UploadOptions = {}): Promise<T> {
    try {
      return await sendUpload<T>(path, formData, options.getAccessToken(), upload);
    } catch (error) {
      if (!(error instanceof ApiError) || !isExpiredToken(error)) throw error;
      const fresh = await options.refreshAccessToken();
      if (!fresh) throw error;
      upload.onProgress?.(0);
      return sendUpload<T>(path, formData, fresh, upload);
    }
  }

  return {
    request,
    get: <T>(path: string, opts?: NoBody) => request<T>(path, { ...opts, method: "GET" }),
    post: <T>(path: string, body?: unknown, opts?: NoBody) => request<T>(path, { ...opts, method: "POST", body }),
    patch: <T>(path: string, body: unknown, opts?: NoBody) => request<T>(path, { ...opts, method: "PATCH", body }),
    delete: (path: string, opts?: NoBody) => request<void>(path, { ...opts, method: "DELETE" }),
    upload: uploadWithRefresh,
  };
}
