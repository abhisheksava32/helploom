"use client";

import Link from "next/link";

import { Logo } from "@/components/brand";
import { ThemeToggle } from "@/components/theme-toggle";
import { ButtonLink } from "@/components/ui/button";
import { useAuth } from "@/lib/auth/auth-context";

const LINKS = [
  { href: "#how-it-works", label: "How it works" },
  { href: "#features", label: "Features" },
  { href: "#pricing", label: "Pricing" },
  { href: "#faq", label: "FAQ" },
];

export function SiteHeader() {
  const { status } = useAuth();
  return (
    <header className="sticky top-0 z-30 border-b border-border/70 bg-background/80 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-4 sm:gap-6 sm:px-6">
        <Logo />
        <nav aria-label="Product" className="hidden md:block">
          <ul className="flex items-center gap-1">
            {LINKS.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  className="rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
                >
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        <div className="ml-auto flex items-center gap-1.5 sm:gap-2">
          <ThemeToggle compact className="hidden sm:inline-flex" />
          {status === "authenticated" ? (
            <ButtonLink href="/app" size="sm">
              Open dashboard
            </ButtonLink>
          ) : (
            <>
              <ButtonLink href="/login" variant="ghost" size="sm">
                Log in
              </ButtonLink>
              <ButtonLink href="/signup" size="sm">
                Start free
              </ButtonLink>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
