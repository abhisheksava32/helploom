import Link from "next/link";

import { cn } from "@/lib/cn";

/** The Helploom mark: a speech bubble woven from two strands, drawn inline so it themes with CSS. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cn("size-7", className)}>
      <rect width="32" height="32" rx="8" className="fill-primary" />
      <path
        d="M9 10.5h14a2.5 2.5 0 0 1 2.5 2.5v6a2.5 2.5 0 0 1-2.5 2.5h-6.2L12 25v-3.5H9A2.5 2.5 0 0 1 6.5 19v-6A2.5 2.5 0 0 1 9 10.5Z"
        className="fill-primary-foreground"
      />
      <path d="M11 14.5h10M11 17.5h6.5" strokeWidth="1.8" strokeLinecap="round" className="stroke-primary" />
    </svg>
  );
}

export function Logo({ href = "/", className }: { href?: string; className?: string }) {
  return (
    <Link
      href={href}
      className={cn("inline-flex items-center gap-2 rounded-md font-semibold tracking-tight", className)}
      aria-label="Helploom home"
    >
      <LogoMark />
      <span className="text-[15px]">Helploom</span>
    </Link>
  );
}
