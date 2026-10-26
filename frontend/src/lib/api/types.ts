/**
 * Types for the API contract in docs/API.md. Names match the "Shared objects" section
 * and fields match the JSON exactly (snake_case), so responses need no mapping layer.
 */

export type Uuid = string;
/** ISO 8601 timestamp in UTC, for example "2026-10-25T20:12:00Z". */
export type Timestamp = string;
/** Calendar date, "YYYY-MM-DD". */
export type DateString = string;
/** Decimal string with six places, for example "0.004120". */
export type MoneyString = string;

export type Role = "owner" | "admin" | "agent";
export type AssistantTone = "friendly" | "professional" | "concise";

// Errors and pagination

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
  };
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface ResultList<T> {
  results: T[];
}

// Accounts

export interface UserRef {
  id: Uuid;
  email: string;
  full_name: string;
}

export interface User extends UserRef {
  date_joined: Timestamp;
}

export interface Organization {
  id: Uuid;
  name: string;
  slug: string;
  assistant_tone: AssistantTone;
  created_at: Timestamp;
  role: Role;
}

export interface AuthResponse {
  access: string;
  user: User;
  organizations: Organization[];
}

export interface MeResponse {
  user: User;
  organizations: Organization[];
}

export interface Member {
  id: Uuid;
  user: UserRef;
  role: Role;
  created_at: Timestamp;
}

export type InvitationStatus = "pending" | "accepted" | "revoked" | "expired";

export interface Invitation {
  id: Uuid;
  email: string;
  role: Role;
  status: InvitationStatus;
  invited_by: UserRef | null;
  expires_at: Timestamp;
  accepted_at: Timestamp | null;
  created_at: Timestamp;
  invite_url: string | null;
}

export interface InvitationPreview {
  organization: { id: Uuid; name: string };
  email: string;
  role: Role;
  status: InvitationStatus;
  expires_at: Timestamp;
  invited_by_name: string;
  account_exists: boolean;
}

// Knowledge

export type DocumentStatus = "queued" | "processing" | "ready" | "failed";

export interface CollectionRef {
  id: Uuid;
  name: string;
}

export interface Collection extends CollectionRef {
  description: string;
  document_count: number;
  created_at: Timestamp;
}

export interface HelpDocument {
  id: Uuid;
  title: string;
  original_filename: string;
  content_type: string;
  file_size: number;
  status: DocumentStatus;
  error_message: string;
  page_count: number | null;
  chunk_count: number;
  token_count: number;
  tags: string[];
  collection: CollectionRef | null;
  embedder: string;
  uploaded_by: UserRef | null;
  created_at: Timestamp;
  updated_at: Timestamp;
  processed_at: Timestamp | null;
}

export type UploadRejectionCode =
  | "file_too_large"
  | "unsupported_file_type"
  | "empty_file"
  | "duplicate_document";

export interface UploadResult {
  documents: HelpDocument[];
  rejected: { filename: string; code: UploadRejectionCode; message: string }[];
}

export interface DocumentText {
  document_id: Uuid;
  title: string;
  text: string;
  char_count: number;
  truncated: boolean;
}

export interface TagCount {
  tag: string;
  count: number;
}

export interface Chunk {
  id: Uuid;
  ordinal: number;
  heading: string;
  location: string;
  page_number: number | null;
  token_count: number;
  text: string;
}

// Assistant

export type Channel = "widget" | "playground";
export type ConversationStatus = "open" | "handed_off" | "closed";
export type MessageRole = "user" | "assistant";
export type MessageStatus = "streaming" | "complete" | "truncated" | "failed";
export type AnswerType = "answered" | "not_found" | "refused" | "error";
export type ProviderName = "ollama" | "claude" | "extractive";
export type Rating = 1 | -1;

export interface Citation {
  marker: number;
  document_id: Uuid | null;
  chunk_id: Uuid | null;
  document_title: string;
  location: string;
  snippet: string;
  score: number | null;
}

export interface Usage {
  input_tokens: number;
  output_tokens: number;
  cache_read_input_tokens: number;
  cache_creation_input_tokens: number;
}

export interface Message {
  id: Uuid;
  role: MessageRole;
  content: string;
  status: MessageStatus;
  answer_type: AnswerType | "";
  reply_to: Uuid | null;
  provider: ProviderName | "";
  model: string;
  latency_ms: number | null;
  first_token_ms: number | null;
  usage: Usage;
  cost_usd: MoneyString;
  rating: Rating | null;
  feedback_comment: string;
  citations: Citation[];
  created_at: Timestamp;
}

export type TicketStatus = "open" | "pending" | "resolved";

export interface Ticket {
  id: Uuid;
  conversation_id: Uuid;
  conversation_title: string;
  status: TicketStatus;
  requester_email: string;
  requester_name: string;
  note: string;
  assigned_to: UserRef | null;
  created_at: Timestamp;
  updated_at: Timestamp;
  resolved_at: Timestamp | null;
}

export interface ConversationSummary {
  id: Uuid;
  channel: Channel;
  status: ConversationStatus;
  title: string;
  message_count: number;
  last_message_at: Timestamp | null;
  created_at: Timestamp;
  started_by: UserRef | null;
  visitor_id: string;
  origin: string;
  page_url: string;
  last_answer_type: AnswerType | "";
  providers: ProviderName[];
  thumbs_up: number;
  thumbs_down: number;
  open_tickets: number;
}

export interface ConversationDetail extends ConversationSummary {
  messages: Message[];
  tickets: Ticket[];
}

export interface ProviderStatus {
  configured: "auto" | ProviderName;
  active: { name: ProviderName; model: string };
  providers: { name: ProviderName; available: boolean; model: string; detail: string }[];
  embedder: {
    configured: "auto" | "ollama" | "hashing";
    active: string;
    dimensions: number;
    stale_documents: number;
  };
}

export interface RetrievalPreview {
  query: string;
  embedder: string;
  threshold: number;
  top_similarity: number | null;
  keyword_hits: number;
  would_answer: boolean;
  results: {
    chunk_id: Uuid;
    document_id: Uuid;
    document_title: string;
    location: string;
    heading: string;
    snippet: string;
    score: number;
    similarity: number | null;
    vector_rank: number | null;
    keyword_rank: number | null;
  }[];
}

// Widget

export type WidgetPosition = "right" | "left";

export interface WidgetSettings {
  site_key: string;
  is_enabled: boolean;
  allowed_origins: string[];
  title: string;
  greeting: string;
  brand_color: string;
  position: WidgetPosition;
  script_url: string;
  ws_url: string;
  embed_snippet: string;
  updated_at: Timestamp;
}

export interface PublicWidgetConfig {
  organization_name: string;
  title: string;
  greeting: string;
  brand_color: string;
  position: WidgetPosition;
  ws_url: string;
}

// Billing

export type PlanCode = "free" | "starter" | "pro";

export interface Plan {
  code: PlanCode;
  name: string;
  price_monthly_cents: number;
  currency: "usd";
  limits: { messages_per_month: number; documents: number; seats: number };
  features: string[];
}

export interface Meter {
  used: number;
  limit: number;
}

export interface UsageSummary {
  period_start: DateString;
  messages: Meter;
  documents: Meter;
  seats: Meter;
}

export interface Subscription {
  plan: Plan;
  status: "active" | "trialing" | "past_due" | "canceled" | "incomplete";
  provider: "demo" | "stripe";
  billing_mode: "demo" | "stripe";
  current_period_start: Timestamp | null;
  current_period_end: Timestamp | null;
  cancel_at_period_end: boolean;
  usage: UsageSummary;
}

export interface CheckoutResult {
  mode: "demo" | "stripe";
  checkout_url: string | null;
  subscription: Subscription;
}

// Analytics (docs/API.md, section 12)

export interface ReportOverview {
  date_from: DateString;
  date_to: DateString;
  conversations: number;
  questions: number;
  answered: number;
  not_found: number;
  refused: number;
  errors: number;
  answer_rate: number;
  not_found_rate: number;
  ratings: { up: number; down: number; average: number | null; satisfaction: number | null };
  avg_latency_ms: number | null;
  avg_first_token_ms: number | null;
  tickets_opened: number;
  cost_usd: MoneyString;
}

export interface DailyPoint {
  date: DateString;
  conversations: number;
  questions: number;
  answered: number;
  not_found: number;
}

export interface DailyReport {
  date_from: DateString;
  date_to: DateString;
  results: DailyPoint[];
}

export interface TopQuestion {
  question: string;
  count: number;
  answered: number;
  not_found: number;
  last_asked_at: Timestamp;
}

export interface TopDocument {
  document_id: Uuid | null;
  title: string;
  citations: number;
  answers: number;
}

export interface UnansweredQuestion {
  message_id: Uuid;
  conversation_id: Uuid;
  question: string;
  channel: Channel;
  asked_at: Timestamp;
  top_similarity: number | null;
  has_ticket: boolean;
}

export interface CostRow {
  provider: ProviderName;
  model: string;
  messages: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_input_tokens: number;
  cache_creation_input_tokens: number;
  cost_usd: MoneyString;
}

export interface CostReport {
  date_from: DateString;
  date_to: DateString;
  results: CostRow[];
  total_cost_usd: MoneyString;
}

// Websocket frames (docs/API.md, section 13)

export interface ErrorFrame {
  type: "error";
  code: string;
  message: string;
  details?: Record<string, unknown>;
  client_message_id?: string;
  message_id?: Uuid;
}

export interface MessageStartFrame {
  type: "message.start";
  client_message_id: string;
  conversation_id: Uuid;
  user_message_id: Uuid;
  message_id: Uuid;
  created_at: Timestamp;
}

export interface MessageDeltaFrame {
  type: "message.delta";
  message_id: Uuid;
  delta: string;
}

export interface MessageCitationsFrame {
  type: "message.citations";
  message_id: Uuid;
  citations: Citation[];
}

export interface MessageDoneFrame {
  type: "message.done";
  message_id: Uuid;
  conversation_id: Uuid;
  status: Exclude<MessageStatus, "streaming">;
  answer_type: AnswerType;
  content: string;
  provider: ProviderName;
  model: string;
  latency_ms: number;
  first_token_ms: number | null;
  usage: Usage;
  cost_usd: MoneyString;
  offer_handoff: boolean;
}

export interface HandoffCreatedFrame {
  type: "handoff.created";
  ticket: { id: Uuid; conversation_id: Uuid; status: TicketStatus; created_at: Timestamp };
}

/** Widget only: sent after the handshake on ws/widget/. */
export interface SessionReadyFrame {
  type: "session.ready";
  visitor_id: string;
  organization_name: string;
  title: string;
  greeting: string;
  brand_color: string;
  position: WidgetPosition;
}

export interface HistoryMessage {
  id: Uuid;
  role: MessageRole;
  content: string;
  answer_type: AnswerType | "";
  rating: Rating | null;
  citations: Citation[];
  created_at: Timestamp;
}

/** Widget only: the reply to conversation.resume. */
export interface ConversationHistoryFrame {
  type: "conversation.history";
  conversation_id: Uuid;
  status: ConversationStatus;
  messages: HistoryMessage[];
}

export interface FeedbackOkFrame {
  type: "feedback.ok";
  message_id: Uuid;
  rating: Rating | null;
}

export type ChatServerFrame =
  | MessageStartFrame
  | MessageDeltaFrame
  | MessageCitationsFrame
  | MessageDoneFrame
  | HandoffCreatedFrame
  | ErrorFrame
  | { type: "auth.ok"; user_id: Uuid; organization_id: Uuid; role: Role }
  | { type: "pong" };

export type ChatClientFrame =
  | { type: "auth"; token: string; organization_id: Uuid | null }
  | {
      type: "chat.message";
      client_message_id: string;
      conversation_id: Uuid | null;
      content: string;
      page_url?: string;
    }
  | { type: "chat.cancel"; message_id: Uuid }
  | { type: "handoff.request"; conversation_id: Uuid; email: string; name?: string; note?: string }
  | { type: "ping" };

export type WidgetServerFrame =
  | ChatServerFrame
  | SessionReadyFrame
  | ConversationHistoryFrame
  | FeedbackOkFrame;

export type WidgetClientFrame =
  | Exclude<ChatClientFrame, { type: "auth" }>
  | { type: "conversation.resume"; conversation_id: Uuid }
  | { type: "feedback"; message_id: Uuid; rating: Rating | null; comment?: string };

export type DashboardEvent =
  | { type: "document.status"; document: HelpDocument }
  | { type: "document.deleted"; document_id: Uuid }
  | { type: "conversation.created"; conversation: ConversationSummary }
  | { type: "conversation.updated"; conversation: ConversationSummary }
  | { type: "ticket.created"; ticket: Ticket }
  | { type: "ticket.updated"; ticket: Ticket }
  | { type: "subscription.updated"; subscription: Subscription };

export type DashboardEventType = DashboardEvent["type"];
