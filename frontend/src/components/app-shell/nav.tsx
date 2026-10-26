"use client";

import {
  BarChart3,
  Code2,
  CreditCard,
  FileText,
  LayoutDashboard,
  LifeBuoy,
  MessagesSquare,
  Settings,
  Sparkles,
  Users,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { ticketsApi } from "@/lib/api/endpoints";
import { cn } from "@/lib/cn";
import { useQuery } from "@/lib/query";
import { useDashboardSocketStatus } from "@/lib/ws/dashboard";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  exact?: boolean;
  badge?: "tickets";
}

const PRIMARY: NavItem[] = [
  { href: "/app", label: "Overview", icon: LayoutDashboard, exact: true },
  { href: "/app/documents", label: "Documents", icon: FileText },
  { href: "/app/playground", label: "Playground", icon: Sparkles },
  { href: "/app/conversations", label: "Conversations", icon: MessagesSquare },
  { href: "/app/tickets", label: "Tickets", icon: LifeBuoy, badge: "tickets" },
  { href: "/app/reports", label: "Reports", icon: BarChart3 },
];

const WORKSPACE: NavItem[] = [
  { href: "/app/settings", label: "Settings", icon: Settings, exact: true },
  { href: "/app/settings/widget", label: "Website widget", icon: Code2 },
  { href: "/app/settings/team", label: "Team", icon: Users },
  { href: "/app/settings/billing", label: "Billing", icon: CreditCard },
];

function isActive(pathname: string, item: NavItem): boolean {
  if (item.exact) return pathname === item.href;
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}

function OpenTicketsBadge() {
  const { data } = useQuery("nav:open-tickets", (signal) => ticketsApi.list({ status: "open", page_size: 1 }, { signal }), {
    tags: ["tickets"],
  });
  if (!data || data.count === 0) return null;
  return (
    <span className="ml-auto rounded-full bg-accent px-1.5 py-px text-xs font-semibold tabular-nums text-accent-foreground">
      <span className="sr-only">, </span>
      {data.count > 99 ? "99+" : data.count}
      <span className="sr-only"> open</span>
    </span>
  );
}

function NavGroup({ items, label, onNavigate }: { items: NavItem[]; label: string; onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <div>
      <p className="px-2.5 pb-1.5 text-xs font-medium text-muted-foreground">{label}</p>
      <ul className="space-y-0.5">
        {items.map((item) => {
          const active = isActive(pathname, item);
          const Icon = item.icon;
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                onClick={onNavigate}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm font-medium transition-colors",
                  active
                    ? "bg-accent text-accent-foreground"
                    : "text-muted-foreground hover:bg-surface-muted hover:text-foreground",
                )}
              >
                <Icon className="size-4 shrink-0" aria-hidden />
                {item.label}
                {item.badge === "tickets" && <OpenTicketsBadge />}
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav aria-label="Dashboard" className="space-y-5 overflow-y-auto">
      <NavGroup items={PRIMARY} label="Help desk" onNavigate={onNavigate} />
      <NavGroup items={WORKSPACE} label="Workspace" onNavigate={onNavigate} />
    </nav>
  );
}

const LIVE_LABELS = {
  idle: { text: "Connecting", tone: "bg-muted-foreground" },
  connecting: { text: "Connecting", tone: "bg-warning" },
  open: { text: "Live updates on", tone: "bg-success" },
  reconnecting: { text: "Reconnecting", tone: "bg-warning" },
  closed: { text: "Live updates off", tone: "bg-danger" },
} as const;

/** Shows whether ws/dashboard/ is connected, so stale data is never a silent surprise. */
export function LiveIndicator() {
  const status = useDashboardSocketStatus();
  const label = LIVE_LABELS[status];
  return (
    <p role="status" className="flex items-center gap-2 px-2.5 text-xs text-muted-foreground">
      <span aria-hidden className="relative flex size-2">
        {status === "open" && <span className={cn("absolute size-full animate-ping rounded-full opacity-50", label.tone)} />}
        <span className={cn("relative size-2 rounded-full", label.tone)} />
      </span>
      {label.text}
    </p>
  );
}
