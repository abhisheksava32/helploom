# Helploom frontend

The marketing site, the staff dashboard and the embeddable website widget. Next.js
16 (App Router) with React 19, TypeScript strict and Tailwind CSS 4. It talks to the
Django backend only through the REST and websocket contract in
[`../docs/API.md`](../docs/API.md).

```bash
cp .env.example .env.local   # optional; the defaults match the local backend
npm install
npm run dev                  # http://localhost:3000 (builds public/widget.js first)
npm run typecheck && npm run lint && npm run build
```

| Script | What it does |
| --- | --- |
| `npm run dev` | Builds the widget, then starts the dev server |
| `npm run build` | Builds the widget, then the production server bundle (`output: "standalone"`) |
| `npm run widget:watch` | Rebuilds `public/widget.js` on every change under `widget/src` |
| `npm run typecheck` / `npm run lint` | Route types (`next typegen`) then `tsc --noEmit` / ESLint with the Next.js and React Compiler rules |

## Configuration

Every variable is in [`.env.example`](.env.example). `NEXT_PUBLIC_` values are inlined
at build time, so the production image takes them as build arguments.

| Variable | Default | Purpose |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend origin; REST lives under `/api/v1` |
| `NEXT_PUBLIC_WS_URL` | `ws://localhost:8000` | Websocket origin |
| `NEXT_PUBLIC_APP_URL` | `http://localhost:3000` | This site's public origin |
| `NEXT_PUBLIC_DEMO_SITE_KEY` | empty | When set, the landing page loads the real widget for that workspace |

## Routes

| Route | Page |
| --- | --- |
| `/` | Landing page: interactive answer preview, how it works, features, pricing from `GET /billing/plans/`, FAQ |
| `/signup`, `/login`, `/invite/[token]` | Auth, including both invitation modes (new account, or signed in) |
| `/app` | Overview: setup checklist, 7 day stats, usage meters, live recent conversations, open tickets |
| `/app/documents` | Drag and drop upload with per file progress, live indexing status, filters, collections, text and passage preview, re-index, delete |
| `/app/playground` | Streaming chat over `ws/chat/` with citation chips, provider badge, latency, ratings, handoff, and a retrieval inspector (`POST /assistant/search/`) |
| `/app/conversations`, `/app/conversations/[id]` | History with filters; transcript with citations, provider, tokens, cost, ratings and tickets |
| `/app/tickets` | Handoff tickets: status, assignee, notes |
| `/app/reports` | Answer rate, conversations per day, answered vs not found, ratings, top questions, top cited documents, content gaps, cost by provider |
| `/app/settings` | Workspace name and tone, answer engine status, profile, password |
| `/app/settings/widget` | Appearance, allowed origins, live preview, embed snippet, site key rotation |
| `/app/settings/team` | Members and roles, invitations |
| `/app/settings/billing` | Plan, usage, upgrades (Stripe Checkout or demo billing) |
| `/widget-demo` | A sample storefront that loads `widget.js` exactly like a customer site |

## Layout

```text
src/
  app/                      routes; each dashboard page is a small server page.tsx
                            (metadata) plus a colocated client *-view.tsx
  components/
    ui/                     hand-built primitives: button, field, dialog and drawer,
                            menu, toast, controls (switch, token input, meter), states
    app-shell/              auth gate, sidebar, organisation switcher, user menu
    chat/                   answer text with citation markers and source cards
    marketing/              landing page sections
  lib/
    api/                    client.ts (the only HTTP code), endpoints.ts, types.ts, errors.ts
    auth/                   session.ts (token, refresh), auth-context.tsx, roles.ts
    ws/                     socket.ts (reconnecting socket), dashboard.tsx (live events)
    chat/use-chat.ts        playground protocol as a pure reducer
    query.ts                data hook with tag invalidation
    citations.ts, origins.ts, format.ts, range.ts
widget/
  src/                      the embeddable widget (TypeScript, no framework)
  build.mjs                 esbuild bundle to public/widget.js
```

## How it works

**Sessions.** The access token lives in memory only (`lib/auth/session.ts`); the
refresh token is an httpOnly cookie the browser sends to `/auth/refresh/`, which
restores the session on load. Refreshes are single flight within a tab and serialised
across tabs with a Web Lock, because the server rotates the refresh token and revokes
the old one: two tabs refreshing at once would otherwise log one of them out. Only a
401 or 403 ends a session; a throttled refresh waits for `Retry-After`, and a network
failure or a rate limit shows a retry screen instead of the login page. A small
"signed in" flag in `localStorage` (no token, just a hint) lets public pages skip the
refresh probe for visitors who never signed in, so the landing page makes no failing
request; dashboard routes always ask the server. The password change request sends
credentials too, because the server answers it with a new refresh cookie.

**API client.** `lib/api/client.ts` is the only module that talks HTTP. It adds the
bearer token and `X-Organization-Id`, parses the error body into a typed `ApiError`
(branch on `code`, never on `message`), retries once after refreshing an expired
token, and uploads with `XMLHttpRequest` because `fetch` cannot report upload progress.

**Data.** `lib/query.ts` is a small hook rather than a library: abortable requests
keyed by their inputs, previous data kept (dimmed) while a filter change loads, local
patches from websocket events, and tag based invalidation. Loading state is derived
from which key has settled, so no effect ever sets state synchronously.

**Real time.** `lib/ws/socket.ts` is a framework free socket shared by the dashboard
and the widget: auth frame handshake (tokens never go in URLs), pings every 25
seconds, a liveness check for sockets that died silently, exponential backoff with
jitter, an immediate retry with a refreshed token after close code 4401, and fatal
codes that stop retrying. The dashboard keeps one `ws/dashboard/` connection per tab;
events patch what is on screen (document status updates rows in place) or invalidate
lists, and every reconnect refetches, because events sent while offline are lost.

**Tenancy in the UI.** Everything under the app shell is keyed by the active
organisation, so switching workspaces remounts the pages and no state from the
previous tenant survives. Role checks only hide what a role cannot do; the server
enforces every rule regardless.

**Widget.** `widget/src` compiles to one IIFE (about 9 KB gzipped) that customers load
with a script tag. It renders inside a Shadow DOM root so neither page's CSS leaks into
the other, inserts all server text as text nodes (never HTML), keeps a random visitor
id and the last conversation in `localStorage` (and works without storage), resumes the
conversation after a reload, rates answers, and offers the handoff form. On phones the
panel goes full screen and the bubble hides behind it; an `invalid_site_key` frame
(rotated key, widget switched off) stops reconnecting for good. It shares
`socket.ts`, `citations.ts` and the contract types with the dashboard through relative
imports, so the protocol is implemented once. `public/widget.js` is a build output and
is not committed.

**Charts.** Reports use recharts with colours from the `--chart-*` tokens, validated for
colour vision deficiency in both themes. Marks stay thin, there is one axis per chart,
every chart has a table view, and refetches keep the previous render instead of
flashing a skeleton.

**Security headers.** `next.config.ts` sends a Content Security Policy whose
`connect-src` allows only this origin and the API, plus `frame-ancestors 'none'`,
`nosniff` and a strict referrer policy. `/widget.js` is served with a short cache and
cross origin resource policy so customer sites can load it.

**Accessibility.** Native `<dialog>` for modals and drawers (focus containment and
Escape for free), the WAI-ARIA menu button pattern for dropdowns, labelled form fields
with described errors, live regions for streaming answers and toasts, visible focus
rings, reduced motion support, and layouts that work down to phone width.
