/**
 * One typed function per endpoint in docs/API.md, grouped by area. Pages call these
 * instead of building paths, so a contract change is a one file edit.
 */

import type { QueryValue } from "@/lib/api/client";
import type {
  AssistantTone,
  CheckoutResult,
  Chunk,
  Collection,
  ConversationDetail,
  ConversationStatus,
  ConversationSummary,
  CostReport,
  DailyReport,
  DocumentText,
  HelpDocument,
  Invitation,
  InvitationPreview,
  Member,
  MeResponse,
  Message,
  Organization,
  Paginated,
  Plan,
  PlanCode,
  ProviderStatus,
  Rating,
  ReportOverview,
  ResultList,
  RetrievalPreview,
  Role,
  Subscription,
  TagCount,
  Ticket,
  TicketStatus,
  TopDocument,
  TopQuestion,
  UnansweredQuestion,
  UploadResult,
  WidgetPosition,
  WidgetSettings,
} from "@/lib/api/types";
import { api } from "@/lib/auth/session";

type Query = Record<string, QueryValue | QueryValue[]>;

interface Signal {
  signal?: AbortSignal;
}

// Account

export const accountApi = {
  me: (opts?: Signal) => api.get<MeResponse>("/auth/me/", opts),
  updateProfile: (body: { full_name: string }) => api.patch<MeResponse>("/auth/me/", body),
  changePassword: (body: { current_password: string; new_password: string }) =>
    api.post<void>("/auth/password/", body, { withCredentials: true }),
  invitation: (token: string, opts?: Signal) =>
    api.get<InvitationPreview>(`/invitations/${encodeURIComponent(token)}/`, { ...opts, auth: false }),
};

// Organization and team

export const organizationApi = {
  get: (opts?: Signal) => api.get<Organization>("/organization/", opts),
  update: (body: { name?: string; assistant_tone?: AssistantTone }) =>
    api.patch<Organization>("/organization/", body),
  members: (query: Query, opts?: Signal) =>
    api.get<Paginated<Member>>("/organization/members/", { ...opts, query }),
  updateMember: (id: string, role: Role) => api.patch<Member>(`/organization/members/${id}/`, { role }),
  removeMember: (id: string) => api.delete(`/organization/members/${id}/`),
  invitations: (query: Query, opts?: Signal) =>
    api.get<Paginated<Invitation>>("/organization/invitations/", { ...opts, query }),
  invite: (body: { email: string; role: Role }) => api.post<Invitation>("/organization/invitations/", body),
  resendInvitation: (id: string) => api.post<Invitation>(`/organization/invitations/${id}/resend/`),
  revokeInvitation: (id: string) => api.delete(`/organization/invitations/${id}/`),
};

// Documents and collections

export const documentsApi = {
  list: (query: Query, opts?: Signal) => api.get<Paginated<HelpDocument>>("/documents/", { ...opts, query }),
  get: (id: string, opts?: Signal) => api.get<HelpDocument>(`/documents/${id}/`, opts),
  upload: (
    files: File[],
    fields: { collectionId?: string; tags?: string[] },
    options: { onProgress?: (fraction: number) => void; signal?: AbortSignal } = {},
  ) => {
    const form = new FormData();
    for (const file of files) form.append("files", file, file.name);
    if (fields.collectionId) form.append("collection_id", fields.collectionId);
    if (fields.tags && fields.tags.length > 0) form.append("tags", fields.tags.join(","));
    return api.upload<UploadResult>("/documents/", form, options);
  },
  update: (id: string, body: { title?: string; tags?: string[]; collection_id?: string | null }) =>
    api.patch<HelpDocument>(`/documents/${id}/`, body),
  remove: (id: string) => api.delete(`/documents/${id}/`),
  reindex: (id: string) => api.post<HelpDocument>(`/documents/${id}/reindex/`),
  text: (id: string, opts?: Signal) => api.get<DocumentText>(`/documents/${id}/text/`, opts),
  chunks: (id: string, query: Query, opts?: Signal) =>
    api.get<Paginated<Chunk>>(`/documents/${id}/chunks/`, { ...opts, query }),
  tags: (opts?: Signal) => api.get<ResultList<TagCount>>("/documents/tags/", opts),
};

export const collectionsApi = {
  list: (query: Query, opts?: Signal) => api.get<Paginated<Collection>>("/collections/", { ...opts, query }),
  create: (body: { name: string; description?: string }) => api.post<Collection>("/collections/", body),
  update: (id: string, body: { name?: string; description?: string }) =>
    api.patch<Collection>(`/collections/${id}/`, body),
  remove: (id: string) => api.delete(`/collections/${id}/`),
};

// Conversations, feedback and tickets

export const conversationsApi = {
  list: (query: Query, opts?: Signal) =>
    api.get<Paginated<ConversationSummary>>("/conversations/", { ...opts, query }),
  get: (id: string, opts?: Signal) => api.get<ConversationDetail>(`/conversations/${id}/`, opts),
  update: (id: string, body: { status: ConversationStatus }) =>
    api.patch<ConversationSummary>(`/conversations/${id}/`, body),
  feedback: (messageId: string, body: { rating: Rating | null; comment?: string }) =>
    api.post<Message>(`/messages/${messageId}/feedback/`, body),
};

export const ticketsApi = {
  list: (query: Query, opts?: Signal) => api.get<Paginated<Ticket>>("/tickets/", { ...opts, query }),
  get: (id: string, opts?: Signal) => api.get<Ticket>(`/tickets/${id}/`, opts),
  update: (id: string, body: { status?: TicketStatus; assigned_to?: string | null; note?: string }) =>
    api.patch<Ticket>(`/tickets/${id}/`, body),
};

// Assistant

export const assistantApi = {
  providers: (opts?: Signal) => api.get<ProviderStatus>("/assistant/providers/", opts),
  search: (body: { query: string; top_k?: number }, opts?: Signal) =>
    api.post<RetrievalPreview>("/assistant/search/", body, opts),
};

// Widget

export const widgetApi = {
  config: (opts?: Signal) => api.get<WidgetSettings>("/widget/config/", opts),
  update: (body: {
    is_enabled?: boolean;
    allowed_origins?: string[];
    title?: string;
    greeting?: string;
    brand_color?: string;
    position?: WidgetPosition;
  }) => api.patch<WidgetSettings>("/widget/config/", body),
  rotateKey: () => api.post<WidgetSettings>("/widget/config/rotate-key/"),
};

// Billing

export const billingApi = {
  plans: (opts?: Signal) => api.get<ResultList<Plan>>("/billing/plans/", { ...opts, auth: false }),
  subscription: (opts?: Signal) => api.get<Subscription>("/billing/subscription/", opts),
  checkout: (plan: PlanCode) => api.post<CheckoutResult>("/billing/checkout/", { plan }),
  portal: () => api.post<{ url: string }>("/billing/portal/"),
};

// Analytics

export interface ReportRange {
  date_from: string;
  date_to: string;
  channel?: "widget" | "playground" | "";
}

export const analyticsApi = {
  overview: (range: ReportRange, opts?: Signal) =>
    api.get<ReportOverview>("/analytics/overview/", { ...opts, query: { ...range } }),
  perDay: (range: ReportRange, opts?: Signal) =>
    api.get<DailyReport>("/analytics/conversations-per-day/", { ...opts, query: { ...range } }),
  topQuestions: (range: ReportRange, limit: number, opts?: Signal) =>
    api.get<ResultList<TopQuestion>>("/analytics/top-questions/", { ...opts, query: { ...range, limit } }),
  topDocuments: (range: ReportRange, limit: number, opts?: Signal) =>
    api.get<ResultList<TopDocument>>("/analytics/top-documents/", { ...opts, query: { ...range, limit } }),
  unanswered: (range: ReportRange, page: number, opts?: Signal) =>
    api.get<Paginated<UnansweredQuestion>>("/analytics/unanswered/", {
      ...opts,
      query: { ...range, page, page_size: 10 },
    }),
  costs: (range: ReportRange, opts?: Signal) =>
    api.get<CostReport>("/analytics/costs/", { ...opts, query: { ...range } }),
};
