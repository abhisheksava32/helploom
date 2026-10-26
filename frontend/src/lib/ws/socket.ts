/**
 * A websocket that stays connected: exponential backoff with jitter, keepalive
 * pings, an optional auth frame handshake, and a liveness check for sockets that
 * died without a close event (laptop sleep, dropped Wi-Fi).
 *
 * Framework free and dependency free on purpose: the dashboard hooks and the
 * embeddable widget bundle share this file. Keep imports relative.
 */

export type SocketStatus = "idle" | "connecting" | "open" | "reconnecting" | "closed";

export interface Frame {
  type: string;
}

export interface ManagedSocketOptions<In extends Frame> {
  /** Called on every attempt, so a rotated key or a new organisation is picked up. */
  url: () => string;
  /**
   * Builds the first frame for sockets that authenticate in-band (docs/API.md:
   * tokens never go in URLs). Return null when there is no session to give up.
   * forceRefresh is true after the server rejected the previous token (close 4401).
   */
  authenticate?: (options: { forceRefresh: boolean }) => Promise<Frame | null>;
  /** The server frame that marks the socket usable, for example "auth.ok". */
  readyType?: string;
  onFrame: (frame: In) => void;
  onStatus?: (status: SocketStatus, closeCode?: number) => void;
  /** Close codes after which reconnecting cannot help (bad site key, origin refused). */
  fatalCodes?: readonly number[];
  pingIntervalMs?: number;
  minBackoffMs?: number;
  maxBackoffMs?: number;
}

const CLOSE_NOT_AUTHENTICATED = 4401;
const CLOSE_TOO_MANY_CONNECTIONS = 4429;
const NORMAL_CLOSURE = 1000;

export class ManagedSocket<In extends Frame, Out extends Frame = Frame> {
  private socket: WebSocket | null = null;
  private stopped = true;
  private ready = false;
  private attempts = 0;
  private forceRefresh = false;
  private retryTimer: ReturnType<typeof setTimeout> | undefined;
  private pingTimer: ReturnType<typeof setInterval> | undefined;
  private lastFrameAt = 0;
  private currentStatus: SocketStatus = "idle";
  private readonly options: Required<Pick<ManagedSocketOptions<In>, "pingIntervalMs" | "minBackoffMs" | "maxBackoffMs">> &
    ManagedSocketOptions<In>;

  constructor(options: ManagedSocketOptions<In>) {
    this.options = { pingIntervalMs: 25_000, minBackoffMs: 500, maxBackoffMs: 30_000, ...options };
  }

  get status(): SocketStatus {
    return this.currentStatus;
  }

  get isReady(): boolean {
    return this.ready && this.socket?.readyState === WebSocket.OPEN;
  }

  start(): void {
    if (!this.stopped) return;
    this.stopped = false;
    this.attempts = 0;
    if (typeof window !== "undefined") window.addEventListener("online", this.handleOnline);
    this.connect();
  }

  stop(): void {
    this.stopped = true;
    if (typeof window !== "undefined") window.removeEventListener("online", this.handleOnline);
    clearTimeout(this.retryTimer);
    this.teardown(NORMAL_CLOSURE);
    this.setStatus("closed");
  }

  /** Closes and reconnects at once, for example after the access token was refreshed. */
  restart(): void {
    if (this.stopped) return this.start();
    clearTimeout(this.retryTimer);
    this.teardown(NORMAL_CLOSURE);
    this.attempts = 0;
    this.connect();
  }

  /** Sends when the socket is ready; returns false (and sends nothing) otherwise. */
  send(frame: Out): boolean {
    if (!this.isReady || !this.socket) return false;
    this.socket.send(JSON.stringify(frame));
    return true;
  }

  private setStatus(status: SocketStatus, closeCode?: number): void {
    if (status === this.currentStatus && closeCode === undefined) return;
    this.currentStatus = status;
    this.options.onStatus?.(status, closeCode);
  }

  private handleOnline = (): void => {
    if (this.currentStatus === "reconnecting") {
      clearTimeout(this.retryTimer);
      this.connect();
    }
  };

  private teardown(code: number): void {
    clearInterval(this.pingTimer);
    this.ready = false;
    const socket = this.socket;
    this.socket = null;
    if (!socket) return;
    socket.onmessage = socket.onclose = socket.onerror = null;
    if (socket.readyState === WebSocket.CONNECTING) {
      // Closing mid handshake makes browsers log an error; close as soon as it opens.
      socket.onopen = () => socket.close(code);
    } else {
      socket.onopen = null;
      if (socket.readyState === WebSocket.OPEN) socket.close(code);
    }
  }

  private connect(): void {
    if (this.stopped) return;
    this.setStatus(this.attempts === 0 ? "connecting" : "reconnecting");
    let socket: WebSocket;
    try {
      socket = new WebSocket(this.options.url());
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.socket = socket;

    socket.onopen = () => {
      this.lastFrameAt = Date.now();
      this.startPings();
      if (this.options.authenticate) {
        const forceRefresh = this.forceRefresh;
        this.options.authenticate({ forceRefresh }).then(
          (frame) => {
            if (this.socket !== socket) return;
            if (!frame) {
              this.stop();
              return;
            }
            socket.send(JSON.stringify(frame));
          },
          () => socket.close(),
        );
      } else if (!this.options.readyType) {
        this.markReady();
      }
    };

    socket.onmessage = (event: MessageEvent) => {
      this.lastFrameAt = Date.now();
      let frame: In;
      try {
        frame = JSON.parse(String(event.data)) as In;
      } catch {
        return; // The protocol is JSON only; ignore anything else.
      }
      if (!frame || typeof frame.type !== "string" || frame.type === "pong") return;
      if (frame.type === this.options.readyType) this.markReady();
      this.options.onFrame(frame);
    };

    socket.onclose = (event: CloseEvent) => {
      if (this.socket !== socket) return;
      this.socket = null;
      this.ready = false;
      clearInterval(this.pingTimer);
      if (this.stopped) return;
      if (this.options.fatalCodes?.includes(event.code)) {
        this.stopped = true;
        this.setStatus("closed", event.code);
        return;
      }
      if (event.code === CLOSE_NOT_AUTHENTICATED && this.options.authenticate && !this.forceRefresh) {
        // Most likely an expired access token: refresh it and retry straight away, once.
        this.forceRefresh = true;
        this.connect();
        return;
      }
      this.scheduleReconnect(event.code);
    };
  }

  private markReady(): void {
    this.ready = true;
    this.attempts = 0;
    this.forceRefresh = false;
    this.setStatus("open");
  }

  private startPings(): void {
    clearInterval(this.pingTimer);
    this.pingTimer = setInterval(() => {
      const socket = this.socket;
      if (!socket || socket.readyState !== WebSocket.OPEN) return;
      if (Date.now() - this.lastFrameAt > this.options.pingIntervalMs * 2.5) {
        // No frame, not even a pong, for over two intervals: the connection is dead.
        socket.close();
        return;
      }
      socket.send(JSON.stringify({ type: "ping" }));
    }, this.options.pingIntervalMs);
  }

  private scheduleReconnect(closeCode?: number): void {
    if (this.stopped) return;
    this.attempts += 1;
    const { minBackoffMs, maxBackoffMs } = this.options;
    const exponential = Math.min(maxBackoffMs, minBackoffMs * 2 ** Math.min(this.attempts, 10));
    // Jitter spreads reconnects out so a server restart is not met by every client at once.
    let delay = exponential / 2 + Math.random() * (exponential / 2);
    if (closeCode === CLOSE_TOO_MANY_CONNECTIONS) delay = Math.max(delay, maxBackoffMs);
    this.setStatus("reconnecting", closeCode);
    clearTimeout(this.retryTimer);
    this.retryTimer = setTimeout(() => this.connect(), delay);
  }
}
