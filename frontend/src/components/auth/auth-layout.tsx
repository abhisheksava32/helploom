import { BookOpenCheck, Quote, ShieldCheck, Zap } from "lucide-react";
import type { ReactNode } from "react";

import { Logo } from "@/components/brand";

const POINTS = [
  { icon: BookOpenCheck, text: "Answers grounded in your own documents, with a citation for every claim." },
  { icon: Zap, text: "Streams in real time on your website and in the dashboard." },
  { icon: ShieldCheck, text: "Says so honestly when the answer is not documented, and hands off to your team." },
];

export function AuthLayout({
  title,
  description,
  children,
  footer,
}: {
  title: string;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-[1fr_minmax(0,560px)]">
      <div className="flex flex-col px-4 py-6 sm:px-8">
        <Logo />
        <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center py-10">
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          {description && <p className="mt-2 text-sm text-muted-foreground">{description}</p>}
          <div className="mt-8">{children}</div>
          {footer && <div className="mt-6 text-sm text-muted-foreground">{footer}</div>}
        </main>
      </div>
      <aside className="relative hidden overflow-hidden border-l border-border bg-surface lg:flex lg:flex-col lg:justify-center lg:px-12">
        <div
          aria-hidden
          className="pointer-events-none absolute -right-24 -top-24 size-96 rounded-full bg-primary/10 blur-3xl"
        />
        <div className="relative max-w-md space-y-8">
          <div>
            <p className="text-sm font-medium text-primary">The help desk that reads your docs</p>
            <p className="mt-3 text-2xl font-semibold leading-snug tracking-tight">
              Customers get answers in seconds. Your team gets the questions nobody documented yet.
            </p>
          </div>
          <ul className="space-y-4">
            {POINTS.map(({ icon: Icon, text }) => (
              <li key={text} className="flex gap-3 text-sm text-muted-foreground">
                <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-accent text-accent-foreground">
                  <Icon className="size-4" aria-hidden />
                </span>
                <span className="pt-1.5">{text}</span>
              </li>
            ))}
          </ul>
          <figure className="rounded-xl border border-border bg-background p-5">
            <Quote className="size-4 text-primary" aria-hidden />
            <blockquote className="mt-2 text-sm leading-relaxed">
              &ldquo;Refunds are issued to the original payment method within 5 business days of the return
              arriving at our warehouse [1].&rdquo;
            </blockquote>
            <figcaption className="mt-3 text-xs text-muted-foreground">
              A typical answer, cited from the returns policy.
            </figcaption>
          </figure>
        </div>
      </aside>
    </div>
  );
}
