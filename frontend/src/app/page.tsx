import {
  ArrowRight,
  BarChart3,
  BookOpenCheck,
  Cpu,
  FileUp,
  Layers,
  LifeBuoy,
  MessageSquareText,
  Radio,
  ShieldCheck,
  Users,
  type LucideIcon,
} from "lucide-react";
import type { Metadata } from "next";

import { Logo } from "@/components/brand";
import { HeroDemo } from "@/components/marketing/hero-demo";
import { LiveWidget } from "@/components/marketing/live-widget";
import { Pricing } from "@/components/marketing/pricing";
import { SiteHeader } from "@/components/marketing/site-header";
import { ButtonLink } from "@/components/ui/button";

export const metadata: Metadata = {
  title: { absolute: "Helploom | The AI help desk that answers from your documents" },
};

const STEPS: { icon: LucideIcon; title: string; body: string; detail: string }[] = [
  {
    icon: FileUp,
    title: "Upload what you already have",
    body: "Drop in policies, handbooks and FAQs as PDF, Word, Markdown, text or HTML.",
    detail: "Text is extracted, split along headings and embedded for search.",
  },
  {
    icon: Layers,
    title: "Helploom finds the right passages",
    body: "Every question runs a semantic search and a keyword search, then fuses the two rankings.",
    detail: "Exact terms like order numbers match as reliably as paraphrases.",
  },
  {
    icon: MessageSquareText,
    title: "Customers get cited answers",
    body: "Answers stream into the widget on your site with a numbered source for every claim.",
    detail: "No good match? It says so and offers a person instead of guessing.",
  },
];

const FEATURES: { icon: LucideIcon; title: string; body: string }[] = [
  {
    icon: BookOpenCheck,
    title: "Citations on every answer",
    body: "Each sentence points at the passage it came from. Click a marker to read the source.",
  },
  {
    icon: LifeBuoy,
    title: "Honest handoff",
    body: "Questions your documents do not cover get a clear reply and a ticket for your team.",
  },
  {
    icon: Radio,
    title: "Real time everywhere",
    body: "Answers stream token by token, and the dashboard updates live as documents index and chats arrive.",
  },
  {
    icon: Cpu,
    title: "Your choice of model",
    body: "Run local models with Ollama, use the Claude API, or answer fully offline from the top passages.",
  },
  {
    icon: BarChart3,
    title: "Reports that find gaps",
    body: "Answer rate, ratings, top questions, cost by provider, and a list of what nobody documented yet.",
  },
  {
    icon: ShieldCheck,
    title: "Built to be trusted",
    body: "Tenant isolation in every query, origin checks and rate limits on the widget, and prompt injection defences.",
  },
  {
    icon: Users,
    title: "Made for teams",
    body: "Owners, admins and agents, invitations by email, and handoff tickets with assignees.",
  },
  {
    icon: MessageSquareText,
    title: "One script tag",
    body: "Paste a snippet and the widget appears in your brand colour, isolated from your site's CSS.",
  },
];

const FAQ = [
  {
    question: "What happens when the answer is not in my documents?",
    answer:
      "Helploom checks how relevant the best passages are before any model runs. Below the threshold it replies that it could not find the answer and offers a handoff, so it never makes up a policy.",
  },
  {
    question: "Which language models does it use?",
    answer:
      "By default a local model through Ollama, so your documents never leave your servers. You can switch to the Claude API, and with no model at all an extractive mode answers from the top passages.",
  },
  {
    question: "Can someone trick the assistant through a document or a question?",
    answer:
      "Passages are fenced off as data, the rules live in a fixed system prompt, and the assistant has no tools or actions. The worst case is a wrong answer with visible citations.",
  },
  {
    question: "How do I add it to my website?",
    answer:
      "Allow your site's origin in the dashboard and paste one script tag before the closing body tag. The widget loads in an isolated Shadow DOM, so it never fights your styles.",
  },
];

export default function HomePage() {
  return (
    <div className="flex min-h-dvh flex-col">
      <SiteHeader />
      <main id="main" className="flex-1">
        <section className="relative overflow-hidden">
          <div
            aria-hidden
            className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[520px] bg-[radial-gradient(ellipse_at_top,var(--accent),transparent_65%)]"
          />
          <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 pb-20 pt-16 sm:px-6 lg:grid-cols-[1.05fr_1fr] lg:pt-24">
            <div>
              <p className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 text-xs font-medium text-muted-foreground shadow-card">
                <span className="size-1.5 rounded-full bg-success" aria-hidden />
                Grounded answers with citations
              </p>
              <h1 className="mt-6 text-4xl font-semibold tracking-tight sm:text-5xl lg:text-[3.4rem] lg:leading-[1.05]">
                Answer every customer question from the documents you already have.
              </h1>
              <p className="mt-6 max-w-xl text-lg text-muted-foreground">
                Helploom turns your policies, handbooks and FAQs into a help desk on your website. It streams cited
                answers in real time and hands off to your team when the answer is not documented.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <ButtonLink href="/signup" size="lg">
                  Start free <ArrowRight className="size-4" aria-hidden />
                </ButtonLink>
                <ButtonLink href="#how-it-works" size="lg" variant="outline">
                  See how it works
                </ButtonLink>
              </div>
              <p className="mt-6 text-sm text-muted-foreground">
                Free plan, no card. Runs on Ollama, the Claude API, or fully offline.
              </p>
            </div>
            <HeroDemo />
          </div>
        </section>

        <section id="how-it-works" className="scroll-mt-20 border-y border-border bg-surface py-20">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <p className="text-sm font-medium text-primary">How it works</p>
            <h2 className="mt-2 max-w-2xl text-3xl font-semibold tracking-tight">From a folder of documents to a live help desk in minutes</h2>
            <ol className="mt-12 grid gap-6 md:grid-cols-3">
              {STEPS.map((step, index) => {
                const Icon = step.icon;
                return (
                  <li key={step.title} className="relative rounded-2xl border border-border bg-background p-6">
                    <div className="flex items-center gap-3">
                      <span className="grid size-10 place-items-center rounded-xl bg-accent text-accent-foreground">
                        <Icon className="size-5" aria-hidden />
                      </span>
                      <span className="text-sm font-medium text-muted-foreground">Step {index + 1}</span>
                    </div>
                    <h3 className="mt-5 font-semibold">{step.title}</h3>
                    <p className="mt-2 text-sm text-muted-foreground">{step.body}</p>
                    <p className="mt-4 border-t border-border pt-4 text-sm">{step.detail}</p>
                  </li>
                );
              })}
            </ol>
          </div>
        </section>

        <section id="features" className="scroll-mt-20 py-20">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <p className="text-sm font-medium text-primary">Features</p>
            <h2 className="mt-2 max-w-2xl text-3xl font-semibold tracking-tight">Everything a support team needs, nothing it has to babysit</h2>
            <ul className="mt-12 grid gap-px overflow-hidden rounded-2xl border border-border bg-border sm:grid-cols-2 lg:grid-cols-4">
              {FEATURES.map((feature) => {
                const Icon = feature.icon;
                return (
                  <li key={feature.title} className="bg-surface p-6">
                    <Icon className="size-5 text-primary" aria-hidden />
                    <h3 className="mt-4 text-sm font-semibold">{feature.title}</h3>
                    <p className="mt-2 text-sm text-muted-foreground">{feature.body}</p>
                  </li>
                );
              })}
            </ul>
          </div>
        </section>

        <section id="pricing" className="scroll-mt-20 border-y border-border bg-surface py-20">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <div className="mx-auto max-w-2xl text-center">
              <p className="text-sm font-medium text-primary">Pricing</p>
              <h2 className="mt-2 text-3xl font-semibold tracking-tight">Start free, upgrade when customers love it</h2>
              <p className="mt-3 text-muted-foreground">
                Every plan includes the widget, citations and handoff. You pay for answered questions, documents and seats.
              </p>
            </div>
            <div className="mt-12">
              <Pricing />
            </div>
          </div>
        </section>

        <section id="faq" className="scroll-mt-20 py-20">
          <div className="mx-auto grid max-w-6xl gap-10 px-4 sm:px-6 lg:grid-cols-[1fr_1.4fr]">
            <div>
              <p className="text-sm font-medium text-primary">FAQ</p>
              <h2 className="mt-2 text-3xl font-semibold tracking-tight">Questions teams ask before they switch it on</h2>
            </div>
            <dl className="divide-y divide-border rounded-2xl border border-border bg-surface">
              {FAQ.map((item) => (
                <div key={item.question} className="p-6">
                  <dt className="font-medium">{item.question}</dt>
                  <dd className="mt-2 text-sm leading-relaxed text-muted-foreground">{item.answer}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        <section className="px-4 pb-20 sm:px-6">
          <div className="mx-auto max-w-6xl rounded-3xl bg-primary px-6 py-14 text-center text-primary-foreground sm:px-12">
            <h2 className="text-3xl font-semibold tracking-tight">Put your documentation to work tonight</h2>
            <p className="mx-auto mt-3 max-w-xl opacity-90">
              Create a workspace, upload a few documents and ask your first question in the playground.
            </p>
            <ButtonLink
              href="/signup"
              size="lg"
              variant="secondary"
              className="mt-8 bg-primary-foreground text-primary hover:bg-primary-foreground/90"
            >
              Create a free workspace
            </ButtonLink>
          </div>
        </section>
      </main>

      <footer className="border-t border-border py-8">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 text-sm text-muted-foreground sm:px-6">
          <Logo />
          <p>Answers from your documents, with sources.</p>
        </div>
      </footer>
      <LiveWidget />
    </div>
  );
}
