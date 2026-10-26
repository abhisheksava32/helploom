"use client";

import { Check, ChevronsUpDown } from "lucide-react";

import { Menu, MenuItem, MenuLabel } from "@/components/ui/menu";
import { useAuth } from "@/lib/auth/auth-context";
import { ROLE_LABELS } from "@/lib/auth/roles";

function OrganizationAvatar({ name }: { name: string }) {
  return (
    <span
      aria-hidden
      className="grid size-8 shrink-0 place-items-center rounded-md bg-surface-muted text-xs font-semibold text-foreground ring-1 ring-inset ring-border"
    >
      {name.slice(0, 2).toUpperCase()}
    </span>
  );
}

function Summary({ name, role }: { name: string; role: string }) {
  return (
    <span className="flex min-w-0 flex-1 items-center gap-2.5 text-left">
      <OrganizationAvatar name={name} />
      <span className="min-w-0">
        <span className="block truncate text-sm font-medium">{name}</span>
        <span className="block text-xs text-muted-foreground">{role}</span>
      </span>
    </span>
  );
}

/** The active workspace; a switcher only when the user belongs to more than one. */
export function OrganizationSwitcher() {
  const { organization, organizations, switchOrganization } = useAuth();
  if (!organization) return null;
  const role = ROLE_LABELS[organization.role];

  if (organizations.length < 2) {
    return (
      <div className="rounded-lg border border-border px-2.5 py-2">
        <Summary name={organization.name} role={role} />
      </div>
    );
  }

  return (
    <Menu
      label={`Workspace: ${organization.name}. Switch workspace`}
      className="w-full"
      triggerClassName="flex w-full items-center gap-2 rounded-lg border border-border px-2.5 py-2 hover:bg-surface-muted"
      trigger={
        <>
          <Summary name={organization.name} role={role} />
          <ChevronsUpDown className="size-4 text-muted-foreground" aria-hidden />
        </>
      }
    >
      <MenuLabel>Switch workspace</MenuLabel>
      {organizations.map((org) => (
        <MenuItem key={org.id} onClick={() => switchOrganization(org.id)} aria-current={org.id === organization.id}>
          <OrganizationAvatar name={org.name} />
          <span className="min-w-0 flex-1">
            <span className="block truncate">{org.name}</span>
            <span className="block text-xs text-muted-foreground">{ROLE_LABELS[org.role]}</span>
          </span>
          {org.id === organization.id && <Check className="size-4 text-primary" aria-hidden />}
        </MenuItem>
      ))}
    </Menu>
  );
}
