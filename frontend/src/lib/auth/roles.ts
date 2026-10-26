"use client";

import type { Role } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/auth-context";

const RANK: Record<Role, number> = { agent: 1, admin: 2, owner: 3 };

/** owner > admin > agent, the same ranking the server's HasOrganizationRole applies. */
export function hasRole(role: Role | undefined, minimum: Role): boolean {
  return role !== undefined && RANK[role] >= RANK[minimum];
}

export const ROLE_LABELS: Record<Role, string> = { owner: "Owner", admin: "Admin", agent: "Agent" };

/**
 * The caller's role in the active organisation. The UI hides what a role cannot
 * do; the server enforces it regardless.
 */
export function usePermissions() {
  const { organization } = useAuth();
  const role = organization?.role;
  return {
    role,
    isAdmin: hasRole(role, "admin"),
    isOwner: hasRole(role, "owner"),
  };
}
