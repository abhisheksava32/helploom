"use client";

import { ChevronsUpDown, ExternalLink, LogOut, UserRound } from "lucide-react";

import { ThemeToggle } from "@/components/theme-toggle";
import { Menu, MenuItem, MenuLink, MenuSeparator } from "@/components/ui/menu";
import { useAuth } from "@/lib/auth/auth-context";
import { initials } from "@/lib/format";

export function UserAvatar({ name, email, className }: { name: string; email: string; className?: string }) {
  return (
    <span
      aria-hidden
      className={`grid size-8 shrink-0 place-items-center rounded-full bg-accent text-xs font-semibold text-accent-foreground ${className ?? ""}`}
    >
      {initials(name, email)}
    </span>
  );
}

export function UserMenu() {
  const { user, logout } = useAuth();
  if (!user) return null;

  return (
    <div className="space-y-2 border-t border-border pt-3">
      <div className="flex items-center justify-between px-2.5">
        <span className="text-xs text-muted-foreground">Theme</span>
        <ThemeToggle compact />
      </div>
      <Menu
        label={`Account menu for ${user.full_name || user.email}`}
        side="top"
        className="w-full"
        triggerClassName="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left hover:bg-surface-muted"
        trigger={
          <>
            <UserAvatar name={user.full_name} email={user.email} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">{user.full_name || "Your account"}</span>
              <span className="block truncate text-xs text-muted-foreground">{user.email}</span>
            </span>
            <ChevronsUpDown className="size-4 text-muted-foreground" aria-hidden />
          </>
        }
      >
        <MenuLink href="/app/settings#profile">
          <UserRound className="size-4" aria-hidden />
          Profile and password
        </MenuLink>
        <MenuLink href="/" target="_blank" rel="noreferrer">
          <ExternalLink className="size-4" aria-hidden />
          Product site
        </MenuLink>
        <MenuSeparator />
        {/* The app shell sends anonymous visitors to /login once the session is cleared. */}
        <MenuItem onClick={() => void logout()}>
          <LogOut className="size-4" aria-hidden />
          Log out
        </MenuItem>
      </Menu>
    </div>
  );
}
