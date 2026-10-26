/**
 * The Helploom website widget: a chat bubble in a Shadow DOM root that talks to
 * ws/widget/ (docs/API.md, section 13). Framework free so the bundle stays small and
 * cannot clash with whatever the host page runs.
 */

import type {
  AnswerType,
  Citation,
  HistoryMessage,
  PublicWidgetConfig,
  Rating,
  WidgetClientFrame,
  WidgetPosition,
  WidgetServerFrame,
} from "../../src/lib/api/types";
import { splitCitations } from "../../src/lib/citations";
import { contrastText } from "../../src/lib/origins";
import { ManagedSocket, type SocketStatus } from "../../src/lib/ws/socket";
import { append, clear, el, icon } from "./dom";
import { randomVisitorId, read, write } from "./storage";
import { STYLES } from "./styles";

export type WidgetTheme = "light" | "dark" | "auto";

export interface WidgetOptions {
  siteKey: string;
  /** Backend origin, for example https://api.example.com (REST lives under /api/v1). */
  apiUrl: string;
  /** Websocket origin; the public config's ws_url wins when the server sends one. */
  wsUrl: string | null;
  theme: WidgetTheme;
  position: WidgetPosition | null;
}

type MessageState = "pending" | "streaming" | "done" | "failed";

interface ChatMessage {
  key: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  state: MessageState;
  answerType: AnswerType | "";
  messageId: string | null;
  clientId: string | null;
  rating: Rating | null;
  offerHandoff: boolean;
  error: string | null;
  expanded: number | null;
  /** The local greeting is not a server message and cannot be rated. */
  local?: boolean;
}

const HANDOFF_TYPES: readonly string[] = ["not_found", "refused", "error"];
const MAX_QUESTION = 2000;

export async function fetchPublicConfig(options: WidgetOptions): Promise<PublicWidgetConfig | null> {
  const url = `${options.apiUrl.replace(/\/$/, "")}/api/v1/widget/public/config/?site_key=${encodeURIComponent(options.siteKey)}`;
  try {
    // No credentials and no custom headers: a simple request, so no CORS preflight.
    const response = await fetch(url, { credentials: "omit" });
    if (response.ok) return (await response.json()) as PublicWidgetConfig;
    if (response.status === 403) {
      console.warn(`[Helploom] ${window.location.origin} is not in this widget's allowed origins. Add it in Settings > Website widget.`);
    } else if (response.status === 404) {
      console.warn("[Helploom] Unknown or disabled site key; the widget is not shown.");
    } else {
      console.warn(`[Helploom] Widget configuration failed with HTTP ${response.status}.`);
    }
  } catch {
    console.warn("[Helploom] Could not reach the Helploom server; the widget is not shown.");
  }
  return null;
}

export class HelploomWidget {
  private readonly options: WidgetOptions;
  private config: PublicWidgetConfig;
  private readonly host: HTMLDivElement;
  private readonly launcher: HTMLButtonElement;
  private readonly badge: HTMLSpanElement;
  private readonly panel: HTMLElement;
  private readonly titleNode: HTMLHeadingElement;
  private readonly subtitleNode: HTMLParagraphElement;
  private readonly notice: HTMLParagraphElement;
  private readonly list: HTMLOListElement;
  private readonly composer: HTMLFormElement;
  private readonly textarea: HTMLTextAreaElement;
  private readonly sendButton: HTMLButtonElement;
  private readonly handoffView: HTMLDivElement;
  private readonly handoffLink: HTMLButtonElement;
  private readonly nodes = new Map<string, HTMLLIElement>();
  private messages: ChatMessage[] = [];
  private socket: ManagedSocket<WidgetServerFrame, WidgetClientFrame> | null = null;
  private visitorId: string;
  private conversationId: string | null;
  private isOpen = false;
  private counter = 0;
  private handoffPending = false;

  constructor(options: WidgetOptions, config: PublicWidgetConfig) {
    this.options = options;
    this.config = config;
    this.visitorId = read(this.storageKey("visitor")) ?? randomVisitorId();
    write(this.storageKey("visitor"), this.visitorId);
    this.conversationId = read(this.storageKey("conversation"));

    this.host = el("div", { id: "helploom-widget", "data-theme": options.theme });
    const root = this.host.attachShadow({ mode: "open" });
    append(root, [el("style", {}, [STYLES])]);

    this.badge = el("span", { class: "badge", hidden: true });
    this.launcher = el("button", { type: "button", class: "launcher", "aria-expanded": "false", "aria-controls": "hl-panel" }, [
      icon("chat", 24),
      this.badge,
    ]);
    this.launcher.addEventListener("click", () => (this.isOpen ? this.close() : this.open()));

    this.titleNode = el("h2", { class: "title", id: "hl-title" });
    this.subtitleNode = el("p", { class: "subtitle" });
    const closeButton = el("button", { type: "button", class: "icon-button", "aria-label": "Close chat" }, [icon("close")]);
    closeButton.addEventListener("click", () => this.close());

    this.notice = el("p", { class: "notice", role: "status", hidden: true });
    this.list = el("ol", { class: "messages", role: "log", "aria-live": "polite", "aria-label": "Conversation" });

    this.textarea = el("textarea", {
      rows: "1",
      maxlength: String(MAX_QUESTION),
      placeholder: "Ask a question",
      "aria-label": "Your question",
    });
    this.textarea.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        this.send();
      }
    });
    this.textarea.addEventListener("input", () => this.updateComposer());
    this.sendButton = el("button", { type: "submit", class: "send", "aria-label": "Send", disabled: true }, [icon("send", 16)]);
    this.composer = el("form", { class: "composer" }, [this.textarea, this.sendButton]);
    this.composer.addEventListener("submit", (event) => {
      event.preventDefault();
      this.send();
    });

    this.handoffView = el("div", { class: "handoff", hidden: true });
    this.handoffLink = el("button", { type: "button", class: "link" }, ["Talk to a human"]);
    this.handoffLink.addEventListener("click", () => this.showHandoff());

    this.panel = el("section", { class: "panel", id: "hl-panel", role: "dialog", "aria-labelledby": "hl-title", hidden: true }, [
      el("header", { class: "header" }, [el("div", { class: "header-text" }, [this.titleNode, this.subtitleNode]), closeButton]),
      this.notice,
      this.list,
      this.handoffView,
      this.composer,
      el("div", { class: "footer" }, [this.handoffLink, el("span", {}, ["Answers cite our help documents"])]),
    ]);
    this.panel.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        this.close();
      }
    });

    append(root, [this.panel, this.launcher]);
    this.applyConfig();
    this.messages.push(this.makeMessage("assistant", config.greeting, { local: true, state: "done" }));
    this.renderAll();
    this.updateHandoffLink();
    document.body.appendChild(this.host);
  }

  open(): void {
    this.isOpen = true;
    this.host.toggleAttribute("data-open", true);
    this.panel.hidden = false;
    this.badge.hidden = true;
    this.launcher.setAttribute("aria-expanded", "true");
    this.launcher.setAttribute("aria-label", "Close chat");
    this.ensureSocket();
    this.scrollToBottom();
    this.textarea.focus();
  }

  close(): void {
    this.isOpen = false;
    this.host.toggleAttribute("data-open", false);
    this.panel.hidden = true;
    this.launcher.setAttribute("aria-expanded", "false");
    this.launcher.setAttribute("aria-label", `Open chat: ${this.config.title}`);
    this.launcher.focus();
  }

  destroy(): void {
    this.socket?.stop();
    this.socket = null;
    this.host.remove();
  }

  // Configuration and appearance

  private storageKey(name: string): string {
    return `helploom:${this.options.siteKey}:${name}`;
  }

  private applyConfig(): void {
    const brand = /^#[0-9a-f]{6}$/i.test(this.config.brand_color) ? this.config.brand_color : "#4f46e5";
    this.host.style.setProperty("--hl-brand", brand);
    this.host.style.setProperty("--hl-on-brand", contrastText(brand));
    this.host.style.setProperty("--hl-chip", `${brand}24`);
    this.host.dataset.position = this.options.position ?? this.config.position;
    this.titleNode.textContent = this.config.title;
    this.subtitleNode.textContent = this.config.organization_name;
    this.launcher.setAttribute("aria-label", this.isOpen ? "Close chat" : `Open chat: ${this.config.title}`);
  }

  private setNotice(text: string | null, tone: "info" | "error" = "info"): void {
    this.notice.hidden = text === null;
    this.notice.textContent = text ?? "";
    this.notice.className = tone === "error" ? "notice error" : "notice";
  }

  // Socket

  private socketUrl(): string {
    const base = this.config.ws_url || `${(this.options.wsUrl ?? "").replace(/\/$/, "")}/ws/widget/`;
    const url = new URL(base, window.location.href);
    url.searchParams.set("site_key", this.options.siteKey);
    url.searchParams.set("visitor_id", this.visitorId);
    return url.toString();
  }

  private ensureSocket(): void {
    if (this.socket) return;
    this.socket = new ManagedSocket<WidgetServerFrame, WidgetClientFrame>({
      url: () => this.socketUrl(),
      readyType: "session.ready",
      fatalCodes: [4403, 4404],
      onStatus: (status, code) => this.onStatus(status, code),
      onFrame: (frame) => this.onFrame(frame),
    });
    this.socket.start();
  }

  private onStatus(status: SocketStatus, code?: number): void {
    if (status === "open") this.setNotice(null);
    else if (status === "reconnecting") this.setNotice("Reconnecting...");
    else if (status === "connecting") this.setNotice("Connecting...");
    else if (status === "closed" && (code === 4403 || code === 4404)) {
      this.setNotice("Chat is not available on this page right now.", "error");
    }
    if (status !== "open") {
      // An answer in flight cannot continue on a new connection.
      for (const message of this.messages) {
        if (message.state === "pending" || message.state === "streaming") {
          message.state = "failed";
          message.error = "The connection dropped. Please ask again.";
          this.render(message);
        }
      }
    }
    this.updateComposer();
  }

  private onFrame(frame: WidgetServerFrame): void {
    switch (frame.type) {
      case "session.ready":
        this.visitorId = frame.visitor_id;
        write(this.storageKey("visitor"), frame.visitor_id);
        this.config = {
          ...this.config,
          organization_name: frame.organization_name,
          title: frame.title,
          greeting: frame.greeting,
          brand_color: frame.brand_color,
          position: frame.position,
        };
        this.applyConfig();
        if (this.conversationId && !this.messages.some((message) => message.messageId)) {
          this.socket?.send({ type: "conversation.resume", conversation_id: this.conversationId });
        }
        break;
      case "conversation.history":
        this.loadHistory(frame.conversation_id, frame.messages);
        break;
      case "message.start": {
        const message = this.find((item) => item.clientId === frame.client_message_id);
        this.setConversation(frame.conversation_id);
        if (message) {
          message.messageId = frame.message_id;
          message.state = "streaming";
          this.render(message);
        }
        break;
      }
      case "message.delta": {
        const message = this.find((item) => item.messageId === frame.message_id);
        if (message) {
          message.content += frame.delta;
          this.render(message);
        }
        break;
      }
      case "message.citations": {
        const message = this.find((item) => item.messageId === frame.message_id);
        if (message) {
          message.citations = frame.citations;
          this.render(message);
        }
        break;
      }
      case "message.done": {
        const message = this.find((item) => item.messageId === frame.message_id);
        this.setConversation(frame.conversation_id);
        if (message) {
          message.content = frame.content;
          message.state = "done";
          message.answerType = frame.answer_type;
          message.offerHandoff = frame.offer_handoff;
          this.render(message);
        }
        if (!this.isOpen) this.badge.hidden = false;
        break;
      }
      case "feedback.ok": {
        const message = this.find((item) => item.messageId === frame.message_id);
        if (message) {
          message.rating = frame.rating;
          this.render(message);
        }
        break;
      }
      case "handoff.created":
        this.handoffPending = false;
        this.showHandoffDone();
        break;
      case "error":
        this.onError(frame);
        break;
      default:
        break;
    }
    this.updateComposer();
  }

  private onError(frame: Extract<WidgetServerFrame, { type: "error" }>): void {
    if (frame.code === "invalid_site_key") {
      // The key was rotated or the widget switched off. Reconnecting cannot help, so
      // stop here instead of relying on the close code that follows.
      this.socket?.stop();
      this.setNotice("Chat is not available on this page right now.", "error");
      return;
    }
    const retry = typeof frame.details?.retry_after === "number" ? Math.ceil(frame.details.retry_after) : null;
    const friendly =
      frame.code === "throttled"
        ? `You are sending messages too fast.${retry ? ` Try again in ${retry} seconds.` : ""}`
        : frame.code === "plan_limit_exceeded"
          ? "We cannot answer new questions right now. Leave your email and our team will reply."
          : frame.message;
    const message = frame.message_id
      ? this.find((item) => item.messageId === frame.message_id)
      : frame.client_message_id
        ? this.find((item) => item.clientId === frame.client_message_id)
        : undefined;

    if (message) {
      message.state = "failed";
      message.error = friendly;
      message.offerHandoff = frame.code === "plan_limit_exceeded" || frame.code === "answer_failed";
      this.render(message);
      return;
    }
    if (frame.code === "not_found" && this.conversationId && !this.messages.some((item) => item.messageId)) {
      // The stored conversation is gone or belongs to someone else: start fresh.
      this.setConversation(null);
      return;
    }
    if (this.handoffPending) {
      this.handoffPending = false;
      const status = this.handoffView.querySelector<HTMLParagraphElement>("[data-role='handoff-error']");
      if (status) {
        status.hidden = false;
        status.textContent = friendly;
      }
      const submit = this.handoffView.querySelector<HTMLButtonElement>("button[type='submit']");
      if (submit) submit.disabled = false;
      return;
    }
    this.setNotice(friendly, "error");
  }

  private setConversation(id: string | null): void {
    this.conversationId = id;
    write(this.storageKey("conversation"), id);
    this.updateHandoffLink();
  }

  private loadHistory(conversationId: string, history: HistoryMessage[]): void {
    this.setConversation(conversationId);
    const restored = history.map((item) =>
      this.makeMessage(item.role, item.content, {
        state: "done",
        messageId: item.id,
        citations: item.citations,
        answerType: item.answer_type,
        rating: item.rating,
        offerHandoff: HANDOFF_TYPES.includes(item.answer_type),
      }),
    );
    this.messages = [this.messages[0], ...restored];
    this.renderAll();
  }

  // Messages

  private makeMessage(role: ChatMessage["role"], content: string, extra: Partial<ChatMessage> = {}): ChatMessage {
    this.counter += 1;
    return {
      key: `m${this.counter}`,
      role,
      content,
      citations: [],
      state: "done",
      answerType: "",
      messageId: null,
      clientId: null,
      rating: null,
      offerHandoff: false,
      error: null,
      expanded: null,
      ...extra,
    };
  }

  private find(predicate: (message: ChatMessage) => boolean): ChatMessage | undefined {
    return this.messages.find(predicate);
  }

  private get streaming(): boolean {
    return this.messages.some((message) => message.state === "pending" || message.state === "streaming");
  }

  private updateComposer(): void {
    const text = this.textarea.value.trim();
    this.sendButton.disabled = !text || this.streaming || !this.socket?.isReady;
  }

  private updateHandoffLink(): void {
    this.handoffLink.disabled = !this.conversationId;
    this.handoffLink.title = this.conversationId ? "" : "Ask a question first so our team has the context.";
  }

  private send(): void {
    const content = this.textarea.value.trim();
    if (!content || this.streaming) return;
    const clientId = `w-${Date.now().toString(36)}-${this.counter + 1}`;
    const question = this.makeMessage("user", content);
    const answer = this.makeMessage("assistant", "", { state: "pending", clientId });
    this.messages.push(question, answer);
    this.render(question);
    this.render(answer);
    const sent = this.socket?.send({
      type: "chat.message",
      client_message_id: clientId,
      conversation_id: this.conversationId,
      content,
      page_url: window.location.href.slice(0, 500),
    });
    if (!sent) {
      answer.state = "failed";
      answer.error = "Not connected yet. Please try again in a moment.";
      this.render(answer);
    }
    this.textarea.value = "";
    this.updateComposer();
    this.scrollToBottom();
  }

  private rate(message: ChatMessage, rating: Rating): void {
    if (!message.messageId) return;
    const next = message.rating === rating ? null : rating;
    this.socket?.send({ type: "feedback", message_id: message.messageId, rating: next });
  }

  private renderAll(): void {
    clear(this.list);
    this.nodes.clear();
    for (const message of this.messages) this.render(message);
    this.scrollToBottom();
  }

  private render(message: ChatMessage): void {
    let node = this.nodes.get(message.key);
    const nearBottom = this.list.scrollHeight - this.list.scrollTop - this.list.clientHeight < 80;
    if (!node) {
      node = el("li", { class: `message ${message.role}` });
      this.nodes.set(message.key, node);
      this.list.appendChild(node);
    }
    clear(node);

    if (message.role === "user") {
      append(node, [el("div", { class: "bubble" }, [message.content])]);
    } else {
      const bubble = el("div", { class: message.state === "failed" ? "bubble failed" : "bubble" });
      if (message.state === "pending" || (message.state === "streaming" && !message.content)) {
        append(bubble, [
          el("span", { class: "dots", role: "status" }, [
            el("span", { class: "sr-only" }, ["Looking through our help documents"]),
            el("span"),
            el("span"),
            el("span"),
          ]),
        ]);
      } else {
        this.appendAnswer(bubble, message);
      }
      if (message.error) append(bubble, [el("p", { class: "error-text", role: "alert" }, [message.error])]);
      append(node, [bubble]);
      if (message.state === "done" || message.state === "failed") this.appendActions(node, message);
    }
    if (nearBottom) this.scrollToBottom();
  }

  private appendAnswer(bubble: HTMLElement, message: ChatMessage): void {
    const byMarker = new Map(message.citations.map((citation) => [citation.marker, citation]));
    const toggle = (marker: number) => {
      message.expanded = message.expanded === marker ? null : marker;
      this.render(message);
    };
    for (const part of splitCitations(message.content)) {
      if (part.kind === "text") {
        bubble.appendChild(document.createTextNode(part.text));
        continue;
      }
      const citation = byMarker.get(part.marker);
      const chip = el(
        "button",
        {
          type: "button",
          class: "cite",
          "aria-expanded": String(message.expanded === part.marker),
          "aria-label": citation ? `Source ${part.marker}: ${citation.document_title}` : `Source ${part.marker}`,
          disabled: !citation,
        },
        [String(part.marker)],
      );
      chip.addEventListener("click", () => toggle(part.marker));
      bubble.appendChild(chip);
    }
    if (message.citations.length > 0 && message.state === "done") {
      const sources = el("div", { class: "sources" });
      for (const citation of [...message.citations].sort((a, b) => a.marker - b.marker)) {
        const label = `${citation.marker}. ${citation.document_title}${citation.location ? `, ${citation.location}` : ""}`;
        const button = el("button", { type: "button", class: "source", "aria-expanded": String(message.expanded === citation.marker) }, [
          label,
        ]);
        button.addEventListener("click", () => toggle(citation.marker));
        sources.appendChild(button);
      }
      bubble.appendChild(sources);
    }
    const expanded = message.expanded === null ? undefined : byMarker.get(message.expanded);
    if (expanded) {
      bubble.appendChild(
        el("div", { class: "snippet" }, [
          el("p", { class: "snippet-title" }, [`${expanded.document_title}${expanded.location ? `, ${expanded.location}` : ""}`]),
          el("p", { class: "snippet-text" }, [expanded.snippet]),
        ]),
      );
    }
  }

  private appendActions(node: HTMLLIElement, message: ChatMessage): void {
    const actions = el("div", { class: "actions" });
    if (message.messageId && message.answerType === "answered") {
      for (const [rating, name, label] of [
        [1, "up", "Helpful"],
        [-1, "down", "Not helpful"],
      ] as const) {
        const button = el("button", { type: "button", class: "action", "aria-label": label, "aria-pressed": String(message.rating === rating) }, [
          icon(name, 14),
        ]);
        button.addEventListener("click", () => this.rate(message, rating));
        actions.appendChild(button);
      }
    }
    if (message.offerHandoff && this.conversationId) {
      const button = el("button", { type: "button", class: "action primary" }, [icon("person", 14), "Talk to a human"]);
      button.addEventListener("click", () => this.showHandoff());
      actions.appendChild(button);
    }
    if (actions.childNodes.length > 0) node.appendChild(actions);
  }

  private scrollToBottom(): void {
    this.list.scrollTop = this.list.scrollHeight;
  }

  // Handoff

  private showChat(): void {
    this.handoffView.hidden = true;
    this.list.hidden = false;
    this.composer.hidden = false;
    this.textarea.focus();
  }

  private showHandoff(): void {
    if (!this.conversationId) return;
    clear(this.handoffView);
    const email = el("input", { type: "email", required: true, autocomplete: "email", maxlength: "254" });
    const name = el("input", { type: "text", autocomplete: "name", maxlength: "150" });
    const note = el("textarea", { maxlength: "2000", placeholder: "Anything our team should know?" });
    const error = el("p", { class: "error-text", role: "alert", hidden: true, "data-role": "handoff-error" });
    const submit = el("button", { type: "submit", class: "button primary" }, ["Send to our team"]);
    const cancel = el("button", { type: "button", class: "button" }, ["Back to chat"]);
    cancel.addEventListener("click", () => this.showChat());
    const form = el("form", {}, [
      el("label", { class: "field" }, ["Email", email]),
      el("label", { class: "field" }, ["Name (optional)", name]),
      el("label", { class: "field" }, ["Message (optional)", note]),
      error,
      el("div", { class: "row" }, [cancel, submit]),
    ]);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!this.conversationId || !email.value.trim()) return;
      const sent = this.socket?.send({
        type: "handoff.request",
        conversation_id: this.conversationId,
        email: email.value.trim(),
        name: name.value.trim() || undefined,
        note: note.value.trim() || undefined,
      });
      error.hidden = Boolean(sent);
      if (!sent) {
        error.textContent = "Not connected. Please try again in a moment.";
        return;
      }
      this.handoffPending = true;
      submit.disabled = true;
    });
    append(this.handoffView, [
      el("h3", {}, ["Talk to a human"]),
      el("p", {}, ["Leave your email and our team will reply with the full conversation in hand."]),
      form,
    ]);
    this.list.hidden = true;
    this.composer.hidden = true;
    this.handoffView.hidden = false;
    email.focus();
  }

  private showHandoffDone(): void {
    clear(this.handoffView);
    const back = el("button", { type: "button", class: "button" }, ["Back to chat"]);
    back.addEventListener("click", () => this.showChat());
    append(this.handoffView, [
      el("h3", {}, ["Thanks, we are on it"]),
      el("p", {}, ["A member of our team will reply by email. You can keep asking questions here in the meantime."]),
      el("div", { class: "row" }, [back]),
    ]);
    this.messages.push(
      this.makeMessage("assistant", "Your request was passed to our team. They will reply by email.", { local: true }),
    );
    this.render(this.messages[this.messages.length - 1]);
    back.focus();
  }
}
