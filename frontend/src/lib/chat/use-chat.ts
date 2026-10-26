"use client";

/**
 * Playground chat over ws/chat/ (docs/API.md, section 13).
 *
 * Frames are folded into state by a pure reducer, so the order rules of the
 * protocol (start, deltas, citations, done, or an error at any point) live in one
 * place. Each question is a "turn" keyed by its client_message_id, which the server
 * echoes back, so the optimistic bubble always meets its answer.
 */

import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import type {
  AnswerType,
  ChatClientFrame,
  ChatServerFrame,
  Citation,
  HandoffCreatedFrame,
  MessageStatus,
  ProviderName,
  Rating,
  Usage,
} from "@/lib/api/types";
import { getFreshAccessToken, getOrganizationId, refreshAccessToken } from "@/lib/auth/session";
import { config } from "@/lib/config";
import { ManagedSocket, type SocketStatus } from "@/lib/ws/socket";

export type AnswerStatus = "pending" | MessageStatus;

export interface ChatError {
  code: string;
  message: string;
  details: Record<string, unknown>;
}

export interface Answer {
  messageId: string | null;
  content: string;
  status: AnswerStatus;
  answerType: AnswerType | null;
  citations: Citation[];
  provider: ProviderName | null;
  model: string;
  latencyMs: number | null;
  firstTokenMs: number | null;
  usage: Usage | null;
  costUsd: string;
  offerHandoff: boolean;
  rating: Rating | null;
  error: ChatError | null;
}

export interface Turn {
  clientId: string;
  question: string;
  userMessageId: string | null;
  answer: Answer;
}

export interface ChatState {
  conversationId: string | null;
  turns: Turn[];
  /** An error not tied to one question (for example "busy"). */
  notice: ChatError | null;
}

type Action =
  | { type: "ask"; clientId: string; question: string }
  | { type: "frame"; frame: ChatServerFrame }
  | { type: "local-error"; clientId: string; error: ChatError }
  | { type: "rated"; messageId: string; rating: Rating | null }
  | { type: "connection-lost" }
  | { type: "reset" }
  | { type: "dismiss-notice" };

const emptyAnswer = (): Answer => ({
  messageId: null,
  content: "",
  status: "pending",
  answerType: null,
  citations: [],
  provider: null,
  model: "",
  latencyMs: null,
  firstTokenMs: null,
  usage: null,
  costUsd: "0.000000",
  offerHandoff: false,
  rating: null,
  error: null,
});

const initialState: ChatState = { conversationId: null, turns: [], notice: null };

function updateTurn(state: ChatState, match: (turn: Turn) => boolean, update: (turn: Turn) => Turn): ChatState {
  let changed = false;
  const turns = state.turns.map((turn) => {
    if (changed || !match(turn)) return turn;
    changed = true;
    return update(turn);
  });
  return changed ? { ...state, turns } : state;
}

const byMessage = (messageId: string) => (turn: Turn) => turn.answer.messageId === messageId;
const byClient = (clientId: string) => (turn: Turn) => turn.clientId === clientId;

export function chatReducer(state: ChatState, action: Action): ChatState {
  switch (action.type) {
    case "ask":
      return {
        ...state,
        notice: null,
        turns: [
          ...state.turns,
          { clientId: action.clientId, question: action.question, userMessageId: null, answer: emptyAnswer() },
        ],
      };
    case "local-error":
      return updateTurn(state, byClient(action.clientId), (turn) => ({
        ...turn,
        answer: { ...turn.answer, status: "failed", error: action.error },
      }));
    case "rated":
      return updateTurn(state, byMessage(action.messageId), (turn) => ({
        ...turn,
        answer: { ...turn.answer, rating: action.rating },
      }));
    case "connection-lost": {
      // An answer in flight cannot resume on a new socket; close it out honestly.
      const lost: ChatError = { code: "connection_lost", message: "The connection dropped before the answer finished.", details: {} };
      const turns = state.turns.map((turn) =>
        turn.answer.status === "pending" || turn.answer.status === "streaming"
          ? { ...turn, answer: { ...turn.answer, status: "failed" as const, error: lost } }
          : turn,
      );
      return { ...state, turns };
    }
    case "reset":
      return initialState;
    case "dismiss-notice":
      return { ...state, notice: null };
    case "frame":
      return applyFrame(state, action.frame);
  }
}

function applyFrame(state: ChatState, frame: ChatServerFrame): ChatState {
  switch (frame.type) {
    case "message.start":
      return {
        ...updateTurn(state, byClient(frame.client_message_id), (turn) => ({
          ...turn,
          userMessageId: frame.user_message_id,
          answer: { ...turn.answer, messageId: frame.message_id, status: "streaming" },
        })),
        conversationId: frame.conversation_id,
      };
    case "message.delta":
      return updateTurn(state, byMessage(frame.message_id), (turn) => ({
        ...turn,
        answer: { ...turn.answer, content: turn.answer.content + frame.delta },
      }));
    case "message.citations":
      return updateTurn(state, byMessage(frame.message_id), (turn) => ({
        ...turn,
        answer: { ...turn.answer, citations: frame.citations },
      }));
    case "message.done":
      return {
        ...updateTurn(state, byMessage(frame.message_id), (turn) => ({
          ...turn,
          answer: {
            ...turn.answer,
            // The final text replaces the stream: invalid markers are removed server side.
            content: frame.content,
            status: frame.status,
            answerType: frame.answer_type,
            provider: frame.provider,
            model: frame.model,
            latencyMs: frame.latency_ms,
            firstTokenMs: frame.first_token_ms,
            usage: frame.usage,
            costUsd: frame.cost_usd,
            offerHandoff: frame.offer_handoff,
          },
        })),
        conversationId: frame.conversation_id,
      };
    case "error": {
      const error: ChatError = { code: frame.code, message: frame.message, details: frame.details ?? {} };
      const match = frame.message_id
        ? byMessage(frame.message_id)
        : frame.client_message_id
          ? byClient(frame.client_message_id)
          : null;
      if (!match) return { ...state, notice: error };
      const next = updateTurn(state, match, (turn) => ({
        ...turn,
        answer: {
          ...turn.answer,
          status: "failed",
          error,
          offerHandoff: turn.answer.offerHandoff || frame.code === "answer_failed",
        },
      }));
      return next === state ? { ...state, notice: error } : next;
    }
    default:
      return state;
  }
}

export interface HandoffInput {
  email: string;
  name?: string;
  note?: string;
}

let clientCounter = 0;
const nextClientId = () => {
  clientCounter += 1;
  return `c-${Date.now().toString(36)}-${clientCounter}`;
};

export function useChat() {
  const [state, dispatch] = useReducer(chatReducer, initialState);
  const [status, setStatus] = useState<SocketStatus>("idle");
  const socketRef = useRef<ManagedSocket<ChatServerFrame, ChatClientFrame> | null>(null);
  const handoffWaiters = useRef<((frame: HandoffCreatedFrame | null, error?: ChatError) => void)[]>([]);

  useEffect(() => {
    const socket = new ManagedSocket<ChatServerFrame, ChatClientFrame>({
      url: () => `${config.wsUrl}/ws/chat/`,
      readyType: "auth.ok",
      authenticate: async ({ forceRefresh }) => {
        const token = forceRefresh ? await refreshAccessToken() : await getFreshAccessToken();
        return token ? { type: "auth", token, organization_id: getOrganizationId() } : null;
      },
      onStatus: (next) => {
        setStatus(next);
        if (next === "reconnecting" || next === "closed") dispatch({ type: "connection-lost" });
      },
      onFrame: (frame) => {
        if (frame.type === "handoff.created") {
          handoffWaiters.current.shift()?.(frame);
          return;
        }
        if (frame.type === "error" && !frame.client_message_id && !frame.message_id && handoffWaiters.current.length) {
          // Handoff failures carry no message ids; hand them to the waiting form.
          handoffWaiters.current.shift()?.(null, { code: frame.code, message: frame.message, details: frame.details ?? {} });
          return;
        }
        dispatch({ type: "frame", frame });
      },
    });
    socketRef.current = socket;
    socket.start();
    return () => {
      socket.stop();
      socketRef.current = null;
    };
  }, []);

  const streaming = state.turns.some(
    (turn) => turn.answer.status === "pending" || turn.answer.status === "streaming",
  );

  const send = useCallback(
    (question: string): boolean => {
      const content = question.trim();
      if (!content) return false;
      const clientId = nextClientId();
      dispatch({ type: "ask", clientId, question: content });
      const sent = socketRef.current?.send({
        type: "chat.message",
        client_message_id: clientId,
        conversation_id: state.conversationId,
        content,
      });
      if (!sent) {
        dispatch({
          type: "local-error",
          clientId,
          error: { code: "not_connected", message: "Not connected to the assistant. Reconnecting...", details: {} },
        });
      }
      return Boolean(sent);
    },
    [state.conversationId],
  );

  const cancel = useCallback(() => {
    const active = state.turns.find((turn) => turn.answer.status === "streaming" && turn.answer.messageId);
    if (active?.answer.messageId) socketRef.current?.send({ type: "chat.cancel", message_id: active.answer.messageId });
  }, [state.turns]);

  const requestHandoff = useCallback(
    (input: HandoffInput): Promise<HandoffCreatedFrame> => {
      const conversationId = state.conversationId;
      return new Promise((resolve, reject) => {
        if (!conversationId) {
          reject(new Error("Ask a question first, then hand the conversation to a person."));
          return;
        }
        const sent = socketRef.current?.send({ type: "handoff.request", conversation_id: conversationId, ...input });
        if (!sent) {
          reject(new Error("Not connected to the assistant. Try again in a moment."));
          return;
        }
        handoffWaiters.current.push((frame, error) =>
          frame ? resolve(frame) : reject(new Error(error?.message ?? "The handoff could not be created.")),
        );
      });
    },
    [state.conversationId],
  );

  const reset = useCallback(() => dispatch({ type: "reset" }), []);
  const dismissNotice = useCallback(() => dispatch({ type: "dismiss-notice" }), []);
  const markRated = useCallback(
    (messageId: string, rating: Rating | null) => dispatch({ type: "rated", messageId, rating }),
    [],
  );

  return { ...state, status, streaming, send, cancel, requestHandoff, reset, dismissNotice, markRated };
}
