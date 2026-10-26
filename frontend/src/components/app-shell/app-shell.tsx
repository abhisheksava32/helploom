"use client";

/**
 * The signed in frame: auth gate, sidebar, mobile navigation and the dashboard
 * socket. Everything below it is keyed by the active organisation, so switching
 * workspaces remounts the pages and no state from the previous tenant survives.
 */

import { Building2, CloudOff, Hourglass, LogOut, Menu as MenuIcon, X } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { Fragment, useEffect, useState, type ReactNode } from "react";

import { Logo, LogoMark } from "@/components/brand";
import { LiveIndicator, NavLinks } from "@/components/app-shell/nav";
import { OrganizationSwitcher } from "@/components/app-shell/organization-switcher";
import { UserMenu } from "@/components/app-shell/user-menu";
import { Button } from "@/components/ui/button";
import { useModal } from "@/components/ui/dialog";
import { Spinner } from "@/components/ui/states";
import { useAuth } from "@/lib/auth/auth-context";
import { DashboardSocketProvider } from "@/lib/ws/dashboard";

export function AppSplash() {
  return (
    <div className="grid min-h-dvh place-items-center bg-background">
      <div className="flex flex-col items-center gap-4">
        <LogoMark className="size-10" />
        <Spinner label="Loading your workspace" />
      </div>
    </div>
  );
}

function NoWorkspace() {
  const { user, logout } = useAuth();
  return (
    <div className="grid min-h-dvh place-items-center px-4">
      <div className="w-full max-w-md rounded-xl border border-border bg-surface p-8 text-center shadow-card">
        <div className="mx-auto mb-4 grid size-12 place-items-center rounded-xl bg-surface-muted text-muted-foreground">
          <Building2 className="size-5" aria-hidden />
        </div>
        <h1 className="text-lg font-semibold">No workspace yet</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {user?.email} is not a member of any workspace. Ask a teammate for an invitation link, or create a
          new account for your business.
        </p>
        <Button variant="outline" className="mt-6" onClick={() => void logout()} icon={<LogOut className="size-4" />}>
          Log out
        </Button>
      </div>
    </div>
  );
}

function ServerUnavailable() {
  const { retry, unavailableReason } = useAuth();
  const throttled = unavailableReason === "throttled";
  return (
    <div className="grid min-h-dvh place-items-center px-4">
      <div role="alert" className="w-full max-w-md rounded-xl border border-border bg-surface p-8 text-center shadow-card">
        <div className="mx-auto mb-4 grid size-12 place-items-center rounded-xl bg-warning-soft text-warning">
          {throttled ? <Hourglass className="size-5" aria-hidden /> : <CloudOff className="size-5" aria-hidden />}
        </div>
        <h1 className="text-lg font-semibold">{throttled ? "Too many sign in requests" : "Cannot reach Helploom"}</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {throttled
            ? "This network restored or started too many sessions in the last minute. You are still signed in; wait a minute, then try again."
            : "The server did not answer, so your session could not be restored. You are still signed in; try again in a moment."}
        </p>
        <Button className="mt-6" onClick={retry}>
          Try again
        </Button>
      </div>
    </div>
  );
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col gap-4 px-3 py-4">
      <div className="px-2">
        <Logo href="/app" />
      </div>
      <OrganizationSwitcher />
      <NavLinks onNavigate={onNavigate} />
      <div className="mt-auto space-y-2">
        <LiveIndicator />
        <UserMenu />
      </div>
    </div>
  );
}

function MobileNav() {
  const [open, setOpen] = useState(false);
  const ref = useModal(open);
  const pathname = usePathname();
  const [lastPath, setLastPath] = useState(pathname);
  // Close on navigation (adjusting state during render instead of in an effect).
  if (pathname !== lastPath) {
    setLastPath(pathname);
    if (open) setOpen(false);
  }

  return (
    <>
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-border bg-surface/90 px-4 backdrop-blur lg:hidden">
        <Logo href="/app" />
        <Button
          variant="ghost"
          size="icon"
          aria-label="Open navigation"
          aria-expanded={open}
          onClick={() => setOpen(true)}
        >
          <MenuIcon className="size-5" aria-hidden />
        </Button>
      </header>
      <dialog
        ref={ref}
        aria-label="Navigation"
        onClose={() => setOpen(false)}
        onClick={(event) => {
          if (event.target === event.currentTarget) setOpen(false);
        }}
        className="hl-slide m-0 h-dvh max-h-dvh w-72 max-w-[85vw] border-r border-border bg-surface p-0 text-foreground backdrop:bg-black/45"
      >
        {open && (
          <div className="relative h-full">
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Close navigation"
              onClick={() => setOpen(false)}
              className="absolute right-3 top-4"
            >
              <X className="size-4" aria-hidden />
            </Button>
            <Sidebar onNavigate={() => setOpen(false)} />
          </div>
        )}
      </dialog>
    </>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { status, user, organization } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (status === "anonymous") router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [status, router, pathname]);

  if (status === "unavailable") return <ServerUnavailable />;
  if (status !== "authenticated" || !user) return <AppSplash />;
  if (!organization) return <NoWorkspace />;

  return (
    <DashboardSocketProvider key={organization.id} organizationId={organization.id}>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2 focus:shadow-popover"
      >
        Skip to content
      </a>
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-64 border-r border-border bg-surface lg:block">
        <Sidebar />
      </aside>
      <MobileNav />
      <div className="lg:pl-64">
        <main id="main" tabIndex={-1} className="mx-auto w-full max-w-7xl px-4 py-6 outline-none sm:px-6 lg:px-8 lg:py-8">
          <Fragment key={organization.id}>{children}</Fragment>
        </main>
      </div>
    </DashboardSocketProvider>
  );
}
