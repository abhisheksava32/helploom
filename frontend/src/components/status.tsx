import { Bot, Cpu, FileSearch, Globe, Sparkles, type LucideIcon } from "lucide-react";

import { Badge, type BadgeTone } from "@/components/ui/badge";
import type {
  AnswerType,
  Channel,
  ConversationStatus,
  DocumentStatus,
  ProviderName,
  TicketStatus,
} from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { providerLabel } from "@/lib/format";

const DOCUMENT: Record<DocumentStatus, { label: string; tone: BadgeTone }> = {
  queued: { label: "Queued", tone: "neutral" },
  processing: { label: "Processing", tone: "warning" },
  ready: { label: "Ready", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
};

export function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  const { label, tone } = DOCUMENT[status];
  return (
    <Badge tone={tone} dot pulse={status === "processing" || status === "queued"}>
      {label}
    </Badge>
  );
}

const ANSWER: Record<AnswerType, { label: string; tone: BadgeTone }> = {
  answered: { label: "Answered", tone: "success" },
  not_found: { label: "Not found", tone: "warning" },
  refused: { label: "Refused", tone: "neutral" },
  error: { label: "Error", tone: "danger" },
};

export function AnswerTypeBadge({ type }: { type: AnswerType | "" | null }) {
  if (!type) return null;
  const { label, tone } = ANSWER[type];
  return <Badge tone={tone}>{label}</Badge>;
}

const CONVERSATION: Record<ConversationStatus, { label: string; tone: BadgeTone }> = {
  open: { label: "Open", tone: "primary" },
  handed_off: { label: "Handed off", tone: "warning" },
  closed: { label: "Closed", tone: "neutral" },
};

export function ConversationStatusBadge({ status }: { status: ConversationStatus }) {
  const { label, tone } = CONVERSATION[status];
  return (
    <Badge tone={tone} dot>
      {label}
    </Badge>
  );
}

const TICKET: Record<TicketStatus, { label: string; tone: BadgeTone }> = {
  open: { label: "Open", tone: "danger" },
  pending: { label: "Pending", tone: "warning" },
  resolved: { label: "Resolved", tone: "success" },
};

export function TicketStatusBadge({ status }: { status: TicketStatus }) {
  const { label, tone } = TICKET[status];
  return (
    <Badge tone={tone} dot>
      {label}
    </Badge>
  );
}

const PROVIDER_ICONS: Record<ProviderName, LucideIcon> = {
  ollama: Cpu,
  claude: Sparkles,
  extractive: FileSearch,
};

/** Which provider answered: shown everywhere an answer is, so model behaviour is never a mystery. */
export function ProviderBadge({
  provider,
  model,
  className,
}: {
  provider: ProviderName | "" | null;
  model?: string;
  className?: string;
}) {
  if (!provider) return null;
  const Icon = PROVIDER_ICONS[provider] ?? Bot;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md bg-surface-muted px-1.5 py-0.5 text-xs font-medium text-muted-foreground",
        className,
      )}
      title={model ? `${providerLabel(provider)}: ${model}` : providerLabel(provider)}
    >
      <Icon className="size-3" aria-hidden />
      {providerLabel(provider)}
      {model && <span className="font-normal text-muted-foreground/80">{model}</span>}
    </span>
  );
}

export function ChannelBadge({ channel }: { channel: Channel }) {
  const Icon = channel === "widget" ? Globe : Sparkles;
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
      <Icon className="size-3.5" aria-hidden />
      {channel === "widget" ? "Website" : "Playground"}
    </span>
  );
}
