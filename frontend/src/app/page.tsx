import Link from "next/link";

import { ThemeToggle } from "@/components/theme-toggle";

const FEATURES = [
  {
    title: "Answers from your documents",
    body: "Upload policies, handbooks and FAQs. Every answer cites the passage it came from.",
  },
  {
    title: "Honest when it does not know",
    body: "Questions your documents do not cover get a clear reply and a handoff to your team.",
  },
  {
    title: "Live on your website",
    body: "One script tag adds a streaming chat widget in your brand colours.",
  },
];

export default function HomePage() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-border bg-surface/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
          <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
            <span aria-hidden className="grid size-7 place-items-center rounded-md bg-primary text-sm text-primary-foreground">
              H
            </span>
            Helploom
          </Link>
          <ThemeToggle />
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col justify-center px-4 py-20 sm:px-6">
        <p className="text-sm font-medium text-primary">AI help desk</p>
        <h1 className="mt-3 max-w-3xl text-4xl font-semibold tracking-tight sm:text-5xl">
          Answer every customer question from the documents you already have.
        </h1>
        <p className="mt-5 max-w-2xl text-lg text-muted-foreground">
          Helploom reads your support library and answers on your website in real time, with citations,
          and hands off to a person when the answer is not in your documentation.
        </p>

        <ul className="mt-14 grid gap-4 sm:grid-cols-3">
          {FEATURES.map((feature) => (
            <li key={feature.title} className="rounded-lg border border-border bg-surface p-5 shadow-card">
              <h2 className="font-medium">{feature.title}</h2>
              <p className="mt-2 text-sm text-muted-foreground">{feature.body}</p>
            </li>
          ))}
        </ul>
      </main>

      <footer className="border-t border-border py-6 text-center text-sm text-muted-foreground">
        Helploom
      </footer>
    </div>
  );
}
