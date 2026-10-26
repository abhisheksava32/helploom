/**
 * Helpers for showing API errors. Branch on error.code, never on the message text:
 * codes are the stable part of the contract.
 */

import { ApiError } from "@/lib/api/client";

export interface PlanLimit {
  limit: "messages" | "documents" | "seats";
  used: number;
  allowed: number;
  plan: string;
}

export function errorMessage(error: unknown, fallback = "Something went wrong. Please try again."): string {
  if (error instanceof ApiError) return error.message || fallback;
  if (error instanceof Error && error.name === "AbortError") return "The request was cancelled.";
  return fallback;
}

export function isApiError(error: unknown, code?: string): error is ApiError {
  return error instanceof ApiError && (code === undefined || error.code === code);
}

/** The structured details of a 402 plan_limit_exceeded (REST) or the matching socket error frame. */
export function planLimitFrom(code: string, details: Record<string, unknown> | undefined): PlanLimit | null {
  if (code !== "plan_limit_exceeded" || !details) return null;
  const { limit, used, allowed, plan } = details;
  if (limit !== "messages" && limit !== "documents" && limit !== "seats") return null;
  return {
    limit,
    used: typeof used === "number" ? used : 0,
    allowed: typeof allowed === "number" ? allowed : 0,
    plan: typeof plan === "string" ? plan : "",
  };
}

export function planLimitOf(error: unknown): PlanLimit | null {
  return error instanceof ApiError ? planLimitFrom(error.code, error.details) : null;
}

export function retryAfterSeconds(details: Record<string, unknown> | undefined): number | null {
  const value = details?.retry_after;
  return typeof value === "number" && value > 0 ? Math.ceil(value) : null;
}

/** First message per field for a validation_error, ready for form inputs. */
export function fieldErrorsOf(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError)) return {};
  const result: Record<string, string> = {};
  for (const [field, messages] of Object.entries(error.fieldErrors())) {
    if (messages[0]) result[field] = messages[0];
  }
  return result;
}
