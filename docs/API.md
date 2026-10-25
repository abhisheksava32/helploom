# Helploom API contract

This document is the binding contract between the backend and the frontend, and
between the two backend owners. If an implementation needs to differ from it, change
this document in the same commit and tell the other owners.

Ownership (each owner changes only its own folders):

| Owner | Folders | Sections in this document |
| --- | --- | --- |
| backend-core | `backend/core`, `backend/helploom`, `backend/accounts`, `backend/widget`, `backend/billing`, `backend/analytics` | Health, Auth, Invitations, Organization, Widget, Billing, Analytics, `ws/dashboard/`, `ws/widget/` |
| backend-ai | `backend/knowledge`, `backend/assistant`, `backend/evals` | Documents, Collections, Conversations, Tickets, Assistant, `ws/chat/`, the shared chat frames |
| frontend | `frontend/` | Consumes everything below; serves `/widget.js` |

Contents

1. [Conventions](#1-conventions)
2. [Shared objects](#2-shared-objects)
3. [Health](#3-health)
4. [Auth](#4-auth)
5. [Invitations](#5-invitations)
6. [Organization](#6-organization)
7. [Documents and collections](#7-documents-and-collections)
8. [Conversations, feedback and tickets](#8-conversations-feedback-and-tickets)
9. [Assistant](#9-assistant)
10. [Widget](#10-widget)
11. [Billing](#11-billing)
12. [Analytics](#12-analytics)
13. [Websockets](#13-websockets)
14. [Real time events](#14-real-time-events)
15. [Endpoint index](#15-endpoint-index)

---

## 1. Conventions

### Base URLs

| What | Local value | Setting |
| --- | --- | --- |
| REST base | `http://localhost:8000/api/v1` | `BACKEND_URL` + `/api/v1` |
| Websocket base | `ws://localhost:8000` | `PUBLIC_WS_URL` |
| Dashboard | `http://localhost:3000` | `FRONTEND_URL` |

Every REST path ends with a slash. Requests without it get a 404.

### Format

- Request and response bodies are JSON (`Content-Type: application/json`), except
  document uploads (`multipart/form-data`).
- Field names are `snake_case`. Ids are UUID strings. Timestamps are ISO 8601 in UTC,
  for example `"2026-10-25T20:12:00.123456Z"`. Dates are `"YYYY-MM-DD"`.
- Money is a decimal string with six places (`"0.004120"`), never a float.
- Optional request fields may be omitted. Response fields are always present; a value
  that does not apply is `null` (objects, numbers, timestamps) or `""` (strings) as
  stated per field.
- `PATCH` is a partial update: send only the fields you change.
- `DELETE` returns `204` with an empty body.

### Authentication

- Dashboard endpoints need `Authorization: Bearer <access token>`.
- The access token is a JWT that lives 15 minutes (`JWT_ACCESS_MINUTES`). The frontend
  keeps it in memory only, never in `localStorage`.
- The refresh token is set by the server as an httpOnly cookie named
  `helploom_refresh`, path `/api/v1/auth/`, `SameSite=Lax`, `Secure` outside DEBUG.
  It lives 14 days and rotates on every refresh; the old one is blacklisted. Page
  scripts never see it. Browser calls that should send or receive it use
  `credentials: "include"`.
- Cookie authenticated endpoints (`/auth/refresh/`, `/auth/logout/`) also require the
  header `X-Requested-With: XMLHttpRequest`. Browsers cannot add a custom header to a
  cross origin request without a CORS preflight, and only the dashboard origin passes
  it, so this blocks cross site request forgery. A missing header returns `403` with
  code `csrf_header_missing`.
- Public endpoints are marked **public**. Everything else returns `401` without a
  valid access token.

### Tenancy and roles

- A user can belong to several organisations. Every dashboard request names the active
  one with `X-Organization-Id: <organization id>`. Without the header the server uses
  the caller's oldest membership. The frontend always sends it.
- Not a member of the named organisation: `403` code `not_a_member`.
- Roles are ranked `owner > admin > agent`. Each endpoint states the minimum role.
  Too low: `403` code `insufficient_role`.
- Every object returned belongs to the active organisation. An id from another
  organisation behaves exactly like an id that does not exist (`404`).

### Pagination

List endpoints marked *paginated* accept `?page=<n>` (from 1) and `?page_size=<n>`
(default 25, maximum 100) and return:

```json
{
  "count": 132,
  "next": "http://localhost:8000/api/v1/documents/?page=3",
  "previous": "http://localhost:8000/api/v1/documents/?page=1",
  "results": []
}
```

`next` and `previous` are `null` at the ends. A page past the end returns `404`.

### Filtering, search and ordering

- Filters are query parameters named after the field (`?status=ready`).
- `?search=<text>` does a case insensitive substring match on the fields listed per
  endpoint.
- `?ordering=<field>` or `?ordering=-<field>` (descending). Allowed fields are listed
  per endpoint; anything else is ignored and the default applies.
- Report endpoints take `?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD`, both inclusive, in
  UTC. Default: the last 30 days ending today. Maximum span: 366 days.

### Errors

Every error, from every endpoint, has this body:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Enter a valid email address.",
    "details": {"email": ["Enter a valid email address."]}
  }
}
```

- `code` is stable and machine readable; branch on it, never on `message`.
- `message` is a friendly sentence that can be shown to the user as is.
- `details` is always an object. For `validation_error` it maps field names to lists
  of messages (`non_field_errors` for errors not tied to one field). Other codes put
  structured context here (see the table).

| Status | Code | When | `details` |
| --- | --- | --- | --- |
| 400 | `validation_error` | Body or query failed validation | field name to messages |
| 400 | `parse_error` | Malformed JSON | `{}` |
| 401 | `not_authenticated` | No access token | `{}` |
| 401 | `token_not_valid` | Expired or invalid access or refresh token | `{}` |
| 401 | `invalid_credentials` | Wrong email or password | `{}` |
| 402 | `plan_limit_exceeded` | The plan's monthly messages, documents or seats are used up | `{"limit": "messages" \| "documents" \| "seats", "used": 200, "allowed": 200, "plan": "free"}` |
| 403 | `permission_denied` | Generic denial | `{}` |
| 403 | `not_a_member` | Caller is not in the named organisation | `{}` |
| 403 | `insufficient_role` | Caller's role is too low | `{}` |
| 403 | `csrf_header_missing` | Cookie endpoint without `X-Requested-With` | `{}` |
| 403 | `origin_not_allowed` | Widget request from an origin the organisation did not allow | `{}` |
| 404 | `not_found` | Unknown path or object | `{}` |
| 405 | `method_not_allowed` | Wrong HTTP method | `{}` |
| 409 | endpoint specific | State conflict, listed per endpoint | varies |
| 413 | `file_too_large` | Upload over `MAX_UPLOAD_MB` | `{"max_bytes": 20971520}` |
| 415 | `unsupported_file_type` | File content is not PDF, DOCX, Markdown, TXT or HTML | `{}` |
| 429 | `throttled` | Rate limit hit; also sent as the `Retry-After` header | `{"retry_after": 12}` |
| 500 | `server_error` | Unexpected failure; never contains internals | `{}` |
| 503 | `service_unavailable` | A dependency such as Stripe is down | `{}` |

Implementation notes for backend owners: raise DRF exceptions (or the ones in
`core.exceptions`) with an explicit `code`; `core.exceptions.exception_handler` builds
the body. A view that answers `401` must keep a JWT authentication class so DRF sends
`WWW-Authenticate` (otherwise DRF turns 401 into 403).

### Rate limits

| Scope | Default | Applies to |
| --- | --- | --- |
| `anon` | 60/min per IP | Public endpoints |
| `user` | 600/min per user | Authenticated endpoints |
| `auth` | 10/min per IP | Signup, login, refresh, password change, invitation accept |
| `upload` | 30/min per user | `POST /documents/` |
| `webhook` | 120/min per IP | Stripe webhook |
| `widget` | 120/min per IP | `GET /widget/public/config/` |
| widget socket | 30 connections/min and 20 messages/min per IP | `ws/widget/` |

---

## 2. Shared objects

These shapes are referenced by name below. Every endpoint that returns one returns
all of its fields.

### UserRef

A user as it appears inside other objects.

```json
{"id": "7b0c...", "email": "ada@example.com", "full_name": "Ada Lovelace"}
```

### User

```json
{
  "id": "7b0c...",
  "email": "ada@example.com",
  "full_name": "Ada Lovelace",
  "date_joined": "2026-10-25T20:12:00Z"
}
```

### Organization

```json
{
  "id": "4f1e...",
  "name": "Northwind Outfitters",
  "slug": "northwind-outfitters",
  "assistant_tone": "friendly",
  "created_at": "2026-10-25T20:12:00Z",
  "role": "owner"
}
```

- `assistant_tone`: `"friendly"` | `"professional"` | `"concise"`.
- `role`: the caller's role in this organisation: `"owner"` | `"admin"` | `"agent"`.
- `slug` is derived from the name at signup, unique, and never changes.

### AuthResponse

Returned by signup, login and invitation accept, together with the refresh cookie.

```json
{
  "access": "<JWT>",
  "user": User,
  "organizations": [Organization]
}
```

`organizations` lists every organisation the user belongs to, oldest membership
first, each with the user's `role`.

### Member

```json
{
  "id": "c2d9...",
  "user": UserRef,
  "role": "admin",
  "created_at": "2026-10-25T20:12:00Z"
}
```

`id` is the membership id, used in member URLs.

### Invitation

```json
{
  "id": "a1b2...",
  "email": "new.teammate@example.com",
  "role": "agent",
  "status": "pending",
  "invited_by": UserRef,
  "expires_at": "2026-11-01T20:12:00Z",
  "accepted_at": null,
  "created_at": "2026-10-25T20:12:00Z",
  "invite_url": "http://localhost:3000/invite/<token>"
}
```

- `status`: `"pending"` | `"accepted"` | `"revoked"` | `"expired"`.
- `invited_by`: `UserRef` or `null` when that user was deleted.
- `invite_url`: the link from the email, filled in only in the responses to create
  and resend while DEBUG is on (so local demos work without email); `null`
  everywhere else. The raw token is never stored, so it cannot be shown again later.

### CollectionRef

```json
{"id": "0d4c...", "name": "Billing"}
```

### Collection

```json
{
  "id": "0d4c...",
  "name": "Billing",
  "description": "Invoices, refunds and payment methods.",
  "document_count": 4,
  "created_at": "2026-10-25T20:12:00Z"
}
```

### Document

```json
{
  "id": "9e8f...",
  "title": "Refund policy",
  "original_filename": "refund-policy.pdf",
  "content_type": "application/pdf",
  "file_size": 182340,
  "status": "ready",
  "error_message": "",
  "page_count": 6,
  "chunk_count": 18,
  "token_count": 5120,
  "tags": ["billing", "policy"],
  "collection": CollectionRef,
  "embedder": "hashing-v1",
  "uploaded_by": UserRef,
  "created_at": "2026-10-25T20:12:00Z",
  "updated_at": "2026-10-25T20:12:09Z",
  "processed_at": "2026-10-25T20:12:09Z"
}
```

- `status`: `"queued"` -> `"processing"` -> `"ready"`, or `"failed"` with a friendly
  reason in `error_message` (for example `"This PDF has no extractable text. It may be
  a scanned image."`). `error_message` is `""` unless failed.
- `content_type`: the type confirmed by content sniffing: `application/pdf`,
  `application/vnd.openxmlformats-officedocument.wordprocessingml.document`,
  `text/markdown`, `text/plain` or `text/html`.
- `page_count`: pages for PDF, `null` for other types and before processing.
- `collection`, `uploaded_by`, `processed_at`: may be `null`.
- `embedder`: name of the embedder that produced the current chunks (`"hashing-v1"`
  or `"ollama:nomic-embed-text"`); `""` before the first successful run.

### Chunk

```json
{
  "id": "5a6b...",
  "ordinal": 0,
  "heading": "Refund window",
  "location": "Page 2",
  "page_number": 2,
  "token_count": 312,
  "text": "Customers can request a refund within 30 days..."
}
```

`location` is a human label: `"Page 2"` for PDF, otherwise the nearest heading path
such as `"Returns > Refund window"`, or `"Section 3"` when there are no headings.
`page_number` is `null` outside PDF.

### Citation

```json
{
  "marker": 1,
  "document_id": "9e8f...",
  "chunk_id": "5a6b...",
  "document_title": "Refund policy",
  "location": "Page 2",
  "snippet": "Customers can request a refund within 30 days of delivery...",
  "score": 0.71
}
```

- `marker` is the `n` of `[n]` in the answer text. Markers keep the passage numbers
  the model saw, so they can skip numbers (`[1]`, `[3]`).
- `document_id` and `chunk_id` become `null` if the document is deleted later; title,
  location and snippet are copies, so history stays readable.
- `snippet`: up to 300 characters of the cited passage.
- `score`: the passage's vector similarity (cosine, 0 to 1), or `null` when it was a
  keyword only match.

### Usage

Token counts for one assistant message. All integers, `0` for local providers that do
not report a field.

```json
{
  "input_tokens": 1830,
  "output_tokens": 164,
  "cache_read_input_tokens": 1024,
  "cache_creation_input_tokens": 0
}
```

### Message

```json
{
  "id": "e3f4...",
  "role": "assistant",
  "content": "You can request a refund within 30 days of delivery [1].",
  "status": "complete",
  "answer_type": "answered",
  "reply_to": "d2e3...",
  "provider": "ollama",
  "model": "llama3.2",
  "latency_ms": 2140,
  "first_token_ms": 380,
  "usage": Usage,
  "cost_usd": "0.000000",
  "rating": 1,
  "feedback_comment": "",
  "citations": [Citation],
  "created_at": "2026-10-25T20:12:00Z"
}
```

- `role`: `"user"` | `"assistant"`.
- `status`: `"streaming"` | `"complete"` | `"truncated"` (hit the token limit or was
  cancelled) | `"failed"`.
- `answer_type`: `"answered"` | `"not_found"` (nothing relevant in the documents) |
  `"refused"` (the model declined) | `"error"`; `""` for user messages.
- `provider`: `"ollama"` | `"claude"` | `"extractive"`; `""` for user messages.
- `model`: the model that actually served the answer (with Claude this can be the
  fallback model); `""` for user messages.
- `reply_to`: for assistant messages, the id of the user message answered; `null` for
  user messages.
- `latency_ms`, `first_token_ms`: `null` for user messages.
- `rating`: `1` (thumbs up), `-1` (thumbs down) or `null`.
- User messages have `usage` all zeros, `cost_usd` `"0.000000"` and `citations` `[]`.

### ConversationSummary

```json
{
  "id": "b7c8...",
  "channel": "widget",
  "status": "open",
  "title": "How long do refunds take?",
  "message_count": 4,
  "last_message_at": "2026-10-25T20:14:00Z",
  "created_at": "2026-10-25T20:12:00Z",
  "started_by": null,
  "visitor_id": "v_5x9...",
  "origin": "https://shop.example.com",
  "page_url": "https://shop.example.com/help",
  "last_answer_type": "answered",
  "providers": ["ollama"],
  "thumbs_up": 1,
  "thumbs_down": 0,
  "open_tickets": 0
}
```

- `channel`: `"widget"` | `"playground"`.
- `status`: `"open"` | `"handed_off"` | `"closed"`.
- `title`: the first question, shortened to 120 characters.
- `started_by`: `UserRef` for playground conversations, `null` for the widget.
- `visitor_id`, `origin`, `page_url`: widget only, `""` for the playground.
- `last_answer_type`: `answer_type` of the latest assistant message, `""` if none.
- `providers`: distinct providers that answered in this conversation.
- `open_tickets`: tickets with status `open` or `pending`.

### ConversationDetail

`ConversationSummary` plus:

```json
{
  "messages": [Message],
  "tickets": [Ticket]
}
```

Messages are oldest first.

### Ticket

```json
{
  "id": "f9a0...",
  "conversation_id": "b7c8...",
  "conversation_title": "How long do refunds take?",
  "status": "open",
  "requester_email": "jo@example.net",
  "requester_name": "Jo",
  "note": "I need to change my delivery address.",
  "assigned_to": UserRef,
  "created_at": "2026-10-25T20:15:00Z",
  "updated_at": "2026-10-25T20:15:00Z",
  "resolved_at": null
}
```

- `status`: `"open"` | `"pending"` | `"resolved"`.
- `assigned_to`, `resolved_at`: may be `null`.

### WidgetSettings

```json
{
  "site_key": "hlp_pk_Jr9...",
  "is_enabled": true,
  "allowed_origins": ["https://shop.example.com"],
  "title": "Help",
  "greeting": "Hi! Ask me anything about our products and policies.",
  "brand_color": "#4f46e5",
  "position": "right",
  "script_url": "http://localhost:3000/widget.js",
  "ws_url": "ws://localhost:8000/ws/widget/",
  "embed_snippet": "<script src=\"http://localhost:3000/widget.js\" data-site-key=\"hlp_pk_Jr9...\" data-api-url=\"http://localhost:8000\" data-ws-url=\"ws://localhost:8000\" defer></script>",
  "updated_at": "2026-10-25T20:12:00Z"
}
```

- `site_key` is public by design (it ships in page source). Origin checks and rate
  limits protect the widget, not secrecy.
- `allowed_origins`: exact origins (`scheme://host[:port]`), normalised to lower case
  without default ports or trailing slash. At most 20.
- `position`: `"right"` | `"left"`.
- `embed_snippet` is built by the server from `FRONTEND_URL`, `BACKEND_URL` and
  `PUBLIC_WS_URL`.

### Plan

```json
{
  "code": "starter",
  "name": "Starter",
  "price_monthly_cents": 2900,
  "currency": "usd",
  "limits": {"messages_per_month": 3000, "documents": 100, "seats": 5},
  "features": ["Everything in Free", "Claude API answers", "Handoff tickets", "Full reports"]
}
```

`code`: `"free"` | `"starter"` | `"pro"`. The catalogue lives in
`backend/billing/plans.py`.

### UsageSummary

```json
{
  "period_start": "2026-10-01",
  "messages": {"used": 120, "limit": 3000},
  "documents": {"used": 14, "limit": 100},
  "seats": {"used": 3, "limit": 5}
}
```

Messages count answered questions this calendar month (UTC). Documents and seats are
live counts; seats include pending invitations.

### Subscription

```json
{
  "plan": Plan,
  "status": "active",
  "provider": "demo",
  "billing_mode": "demo",
  "current_period_start": null,
  "current_period_end": null,
  "cancel_at_period_end": false,
  "usage": UsageSummary
}
```

- `status`: `"active"` | `"trialing"` | `"past_due"` | `"canceled"` | `"incomplete"`.
- `provider`: who manages this subscription: `"demo"` | `"stripe"`.
- `billing_mode`: how the server runs: `"stripe"` when `STRIPE_SECRET_KEY` is set,
  otherwise `"demo"`. The UI shows a clear "Demo billing" label in demo mode.
- Period fields are `null` in demo mode.

---

## 3. Health

Owner: backend-core.

### `GET /health/` (public)

`200` when the database answers and pgvector is installed, else `503`, same body:

```json
{"status": "ok", "version": "0.1.0", "database": "ok", "pgvector": true}
```

`status`: `"ok"` | `"degraded"`. `database`: `"ok"` | `"unavailable"`.

---

## 4. Auth

Owner: backend-core. Throttle scope `auth` on signup, login, refresh, password.

### `POST /auth/signup/` (public)

Creates the user, a new organisation with the user as owner, a Free subscription and
the widget settings, in one transaction.

```json
{
  "email": "ada@example.com",
  "password": "a long passphrase",
  "full_name": "Ada Lovelace",
  "organization_name": "Northwind Outfitters"
}
```

- `email`: required, unique ignoring case (stored lower case).
- `password`: required, Django password validators (at least 10 characters, not too
  common, not all digits, not similar to the email).
- `full_name`: optional, up to 150 characters.
- `organization_name`: required, 2 to 150 characters.

`201` `AuthResponse` and the refresh cookie. Errors: `400 validation_error` (for
example `details.email: ["An account with this email already exists."]`).

### `POST /auth/login/` (public)

```json
{"email": "ada@example.com", "password": "a long passphrase"}
```

`200` `AuthResponse` and the refresh cookie. Errors: `401 invalid_credentials` (same
message for unknown email and wrong password), `400 validation_error`.

### `POST /auth/refresh/` (public, cookie)

Header `X-Requested-With: XMLHttpRequest`; no body. Reads the refresh cookie.

`200` and a rotated refresh cookie:

```json
{"access": "<JWT>"}
```

Errors: `401 token_not_valid` (missing, expired or blacklisted cookie; the cookie is
cleared), `403 csrf_header_missing`.

### `POST /auth/logout/` (public, cookie)

Header `X-Requested-With: XMLHttpRequest`; no body. Blacklists the refresh token if
present and clears the cookie. Always `204`, even without a cookie.

### `GET /auth/me/`

`200`:

```json
{"user": User, "organizations": [Organization]}
```

### `PATCH /auth/me/`

```json
{"full_name": "Ada King"}
```

`200`, same body as `GET /auth/me/`.

### `POST /auth/password/`

```json
{"current_password": "old one", "new_password": "a new long passphrase"}
```

`204`. Other sessions keep working until their access token expires. Errors:
`400 validation_error` (`details.current_password` when wrong, `details.new_password`
when it fails the validators).

---

## 5. Invitations

Owner: backend-core. Invited people open `FRONTEND_URL/invite/<token>`, which calls
these two endpoints. `<token>` is the raw token from the email link.

### `GET /invitations/<token>/` (public)

`200`:

```json
{
  "organization": {"id": "4f1e...", "name": "Northwind Outfitters"},
  "email": "new.teammate@example.com",
  "role": "agent",
  "status": "pending",
  "expires_at": "2026-11-01T20:12:00Z",
  "invited_by_name": "Ada Lovelace",
  "account_exists": false
}
```

`account_exists` tells the page whether to ask for a password to create an account or
to ask the person to log in first. Errors: `404 not_found` for an unknown token.

### `POST /invitations/<token>/accept/` (public or authenticated; throttle `auth`)

Two modes:

- **Signed in** (sends `Authorization`): body `{}`. The signed in user's email must
  match the invitation's email (ignoring case).
- **New account** (no `Authorization`): body
  `{"full_name": "Grace Hopper", "password": "a long passphrase"}`. Creates the user
  with the invitation's email.

Both return `200` `AuthResponse` with the refresh cookie; the new membership is in
`organizations`.

Errors:

| Status | Code | When |
| --- | --- | --- |
| 404 | `not_found` | Unknown token |
| 409 | `invitation_not_pending` | Accepted, revoked or expired; `details.status` says which |
| 409 | `account_exists` | New account mode but a user with this email exists: log in first |
| 403 | `email_mismatch` | Signed in mode with a different email |
| 409 | `already_member` | The user is already in the organisation |
| 400 | `validation_error` | Password fails the validators |

---

## 6. Organization

Owner: backend-core. All endpoints act on the organisation named by
`X-Organization-Id`.

### `GET /organization/` (agent)

`200` `Organization`.

### `PATCH /organization/` (admin)

```json
{"name": "Northwind", "assistant_tone": "professional"}
```

`200` `Organization`. The new name is used as the business name in the assistant's
system prompt from the next question on.

### `GET /organization/members/` (agent, paginated)

Results: `Member`. `?search=` matches email and full name. `?role=` filters.
Ordering: `created_at` (default), `email`, `role`.

### `PATCH /organization/members/<membership_id>/` (owner)

```json
{"role": "admin"}
```

`200` `Member`. Errors: `409 last_owner` when this would leave no owner.

### `DELETE /organization/members/<membership_id>/` (admin; any role for yourself)

Removes a member. Removing an owner needs the owner role. Anyone may remove their own
membership (leave). `204`. Errors: `409 last_owner`, `403 insufficient_role`.

### `GET /organization/invitations/` (admin, paginated)

Results: `Invitation` (with `invite_url` `null`). `?status=pending|accepted|revoked|expired`.
Ordering: `-created_at` (default).

### `POST /organization/invitations/` (admin)

```json
{"email": "new.teammate@example.com", "role": "agent"}
```

- `role`: `"admin"` or `"agent"`; `"owner"` only when the caller is an owner.

Emails the invite link (console email backend in development; the link is printed in
the server log). `201` `Invitation` (with `invite_url` in DEBUG). Expires after
`INVITATION_EXPIRY_DAYS` (7).

Errors: `402 plan_limit_exceeded` (`limit: "seats"`; pending invitations count as
seats), `409 already_member`, `409 already_invited` (a pending invitation exists;
use resend), `400 validation_error`.

### `POST /organization/invitations/<id>/resend/` (admin)

Issues a new token and expiry for a pending or expired invitation and emails it again.
`200` `Invitation`. Errors: `409 invitation_not_pending` for accepted or revoked ones.

### `DELETE /organization/invitations/<id>/` (admin)

Revokes a pending invitation. `204`. Errors: `409 invitation_not_pending`.

---

## 7. Documents and collections

Owner: backend-ai. Status changes are also pushed live on `ws/dashboard/`
(`document.status`, `document.deleted`).

### `GET /documents/` (agent, paginated)

Results: `Document`.

| Parameter | Meaning |
| --- | --- |
| `status` | `queued` \| `processing` \| `ready` \| `failed` |
| `collection` | a collection id, or `none` for documents without one |
| `tag` | documents that have this tag |
| `search` | title and original filename |
| `ordering` | `created_at`, `title`, `file_size`, `chunk_count`, `status` (default `-created_at`) |

### `POST /documents/` (admin, multipart, throttle `upload`)

Form fields:

| Field | Required | Meaning |
| --- | --- | --- |
| `files` | yes | One or more files, the same field repeated. At most `MAX_FILES_PER_UPLOAD` (10) |
| `collection_id` | no | Put every file in this collection |
| `tags` | no | Comma separated, for example `billing,policy`. Lower cased, trimmed, at most 10 tags of 50 characters |

Each file is checked on its own: size up to `MAX_UPLOAD_MB` (20), type sniffed from
the bytes (PDF, DOCX, Markdown, TXT, HTML; the extension must agree), not empty, not
a byte for byte duplicate of a document already in the organisation. Accepted files
are stored and queued for ingestion; the title is the filename without its extension.

`201` when at least one file was accepted:

```json
{
  "documents": [Document],
  "rejected": [
    {"filename": "logo.png", "code": "unsupported_file_type", "message": "logo.png is not a PDF, DOCX, Markdown, TXT or HTML file."}
  ]
}
```

Per file codes in `rejected`: `file_too_large`, `unsupported_file_type`,
`empty_file`, `duplicate_document`.

Errors for the whole request: `400 upload_rejected` when no file was accepted
(`details.rejected` holds the list above), `400 validation_error` (no files, too many
files, unknown `collection_id`), `402 plan_limit_exceeded` (`limit: "documents"`,
checked against the number of files sent before anything is stored).

### `GET /documents/tags/` (agent)

Every tag in use with its document count, most used first. Not paginated.

```json
{"results": [{"tag": "billing", "count": 6}]}
```

### `GET /documents/<id>/` (agent)

`200` `Document`.

### `PATCH /documents/<id>/` (admin)

```json
{"title": "Refunds and returns", "tags": ["billing"], "collection_id": null}
```

`collection_id: null` removes the document from its collection. `200` `Document`.

### `DELETE /documents/<id>/` (admin)

Deletes the file, its chunks and its vectors. Past citations keep their copied title
and snippet. `204`.

### `POST /documents/<id>/reindex/` (admin)

Re-extracts, re-chunks and re-embeds with the current embedder. `202` `Document`
with `status: "queued"`. Errors: `409 document_busy` while queued or processing,
unless the job looks stuck (no update for 15 minutes, for example after a restart
lost the in-process queue), in which case it is queued again.

### `GET /documents/<id>/text/` (agent)

The extracted text for the preview pane.

```json
{
  "document_id": "9e8f...",
  "title": "Refund policy",
  "text": "Refund policy\n\nCustomers can...",
  "char_count": 21844,
  "truncated": false
}
```

`text` is at most 200,000 characters (`truncated: true` beyond that) and `""` before
extraction.

### `GET /documents/<id>/chunks/` (agent, paginated)

Results: `Chunk`, by `ordinal`.

### `GET /collections/` (agent, paginated)

Results: `Collection`, by name. `?search=` matches the name.

### `POST /collections/` (admin)

```json
{"name": "Billing", "description": "Invoices, refunds and payment methods."}
```

`201` `Collection`. Errors: `400 validation_error` when the name is taken.

### `PATCH /collections/<id>/` (admin)

Same fields, partial. `200` `Collection`.

### `DELETE /collections/<id>/` (admin)

The collection's documents stay and lose their collection. `204`.

---

## 8. Conversations, feedback and tickets

Owner: backend-ai. New conversations and tickets are also pushed on `ws/dashboard/`.

### `GET /conversations/` (agent, paginated)

Results: `ConversationSummary`.

| Parameter | Meaning |
| --- | --- |
| `channel` | `widget` \| `playground` |
| `status` | `open` \| `handed_off` \| `closed` |
| `answer_type` | conversations with at least one assistant message of this type, for example `not_found` |
| `rating` | `up` \| `down`: conversations with at least one such rating |
| `provider` | `ollama` \| `claude` \| `extractive` |
| `has_ticket` | `true` \| `false` |
| `date_from`, `date_to` | by `created_at`, inclusive |
| `search` | message content and title |
| `ordering` | `last_message_at` (default `-last_message_at`), `created_at`, `message_count` |

### `GET /conversations/<id>/` (agent)

`200` `ConversationDetail`.

### `PATCH /conversations/<id>/` (agent)

```json
{"status": "closed"}
```

`200` `ConversationSummary`.

### `POST /messages/<id>/feedback/` (agent)

Rate an assistant message from the dashboard. Widget visitors rate over the socket.

```json
{"rating": -1, "comment": "Cited the wrong policy."}
```

`rating`: `1`, `-1` or `null` (clears it). `comment`: optional, up to 1000
characters. `200` `Message`. Errors: `400 validation_error` for user messages.

### `GET /tickets/` (agent, paginated)

Results: `Ticket`.

| Parameter | Meaning |
| --- | --- |
| `status` | `open` \| `pending` \| `resolved` |
| `assigned_to` | a user id, `me`, or `none` |
| `search` | requester email, name and note |
| `ordering` | `created_at` (default `-created_at`), `status` |

### `GET /tickets/<id>/` (agent)

`200` `Ticket`.

### `PATCH /tickets/<id>/` (agent)

```json
{"status": "resolved", "assigned_to": "7b0c...", "note": "Refunded manually."}
```

- `assigned_to`: a member's user id or `null`. Not a member: `400 validation_error`.
- Setting `status` to `resolved` sets `resolved_at`; moving away clears it.

`200` `Ticket`.

---

## 9. Assistant

Owner: backend-ai. Questions are asked over `ws/chat/` (dashboard playground) or
`ws/widget/` (public), not over REST.

### `GET /assistant/providers/` (agent)

Drives the provider status panel in settings and the provider badge in the
playground. Probes are cached for `PROVIDER_PROBE_TTL_SECONDS` (30).

```json
{
  "configured": "auto",
  "active": {"name": "ollama", "model": "llama3.2"},
  "providers": [
    {"name": "ollama", "available": true, "model": "llama3.2", "detail": "Reachable at http://localhost:11434."},
    {"name": "claude", "available": false, "model": "claude-opus-5-5", "detail": "ANTHROPIC_API_KEY is not set."},
    {"name": "extractive", "available": true, "model": "extractive-v1", "detail": "Offline answers built from the top passages."}
  ],
  "embedder": {
    "configured": "auto",
    "active": "hashing-v1",
    "dimensions": 768,
    "stale_documents": 0
  }
}
```

- `configured`: the `LLM_PROVIDER` setting: `"auto"` | `"ollama"` | `"claude"` |
  `"extractive"`.
- `active`: the provider the next question will use.
- `detail`: one human sentence; never contains secrets.
- `embedder.active`: `"hashing-v1"` or `"ollama:nomic-embed-text"`.
  `stale_documents` counts ready documents embedded with a different embedder (run
  `uv run python manage.py reembed` to fix).

### `POST /assistant/search/` (agent)

Runs retrieval only, for the playground's "show sources" view and for tuning.

```json
{"query": "how long do refunds take", "top_k": 5}
```

`top_k`: optional, 1 to 20, default `RETRIEVAL_TOP_K`.

```json
{
  "query": "how long do refunds take",
  "embedder": "hashing-v1",
  "threshold": 0.3,
  "top_similarity": 0.71,
  "keyword_hits": 3,
  "would_answer": true,
  "results": [
    {
      "chunk_id": "5a6b...",
      "document_id": "9e8f...",
      "document_title": "Refund policy",
      "location": "Page 2",
      "heading": "Refund window",
      "snippet": "Customers can request a refund within 30 days...",
      "score": 0.0325,
      "similarity": 0.71,
      "vector_rank": 1,
      "keyword_rank": 2
    }
  ]
}
```

- `score`: the fused reciprocal rank fusion score (higher is better).
- `similarity`: cosine similarity, `null` when the passage came only from keyword
  search. `vector_rank` and `keyword_rank` are 1 based, `null` when absent from that
  side.
- `threshold`: the relevance threshold in effect for this embedder.
- `would_answer`: the relevance decision the chat pipeline would make
  (`top_similarity >= threshold`).

---

## 10. Widget

Owner: backend-core.

### `GET /widget/config/` (agent)

`200` `WidgetSettings`.

### `PATCH /widget/config/` (admin)

```json
{
  "is_enabled": true,
  "allowed_origins": ["https://shop.example.com", "https://www.shop.example.com"],
  "title": "Northwind help",
  "greeting": "Hi! How can we help?",
  "brand_color": "#0f766e",
  "position": "right"
}
```

- `allowed_origins`: each must be `http(s)://host[:port]` with no path, query or
  credentials; stored normalised, duplicates removed, at most 20.
  Invalid entries: `400 validation_error` with `details.allowed_origins`.
- `title`: 1 to 60 characters. `greeting`: 1 to 300. `brand_color`: `#rrggbb`.

`200` `WidgetSettings`.

### `POST /widget/config/rotate-key/` (admin)

Issues a new site key. The old key stops working immediately, including open
sockets on their next message. `200` `WidgetSettings`.

### `GET /widget/public/config/?site_key=<key>` (public, throttle `widget`)

Called by `widget.js` on the customer's page to draw the bubble before any socket
opens. Sends no credentials and no custom headers, so no CORS preflight happens.

The browser's `Origin` header must be one of the organisation's `allowed_origins`
(while DEBUG and `WIDGET_ALLOW_LOCALHOST_IN_DEBUG` are on, any `http://localhost:*`
or `http://127.0.0.1:*` origin is also allowed). The response then carries
`Access-Control-Allow-Origin: <that origin>` and `Vary: Origin`; never `*`.

`200`:

```json
{
  "organization_name": "Northwind Outfitters",
  "title": "Help",
  "greeting": "Hi! Ask me anything about our products and policies.",
  "brand_color": "#4f46e5",
  "position": "right",
  "ws_url": "ws://localhost:8000/ws/widget/"
}
```

Errors: `404 not_found` (unknown key or widget disabled), `403 origin_not_allowed`
(missing or unlisted `Origin`).

### Embedding

The dashboard shows `embed_snippet`; customers paste it before `</body>`:

```html
<script src="http://localhost:3000/widget.js" data-site-key="hlp_pk_..." data-api-url="http://localhost:8000" data-ws-url="ws://localhost:8000" defer></script>
```

`widget.js` (owner: frontend) reads the `data-` attributes, fetches the public
config, renders a floating bubble inside a Shadow DOM root (so the host page's CSS
cannot leak in or out), and opens `ws/widget/` when the visitor opens the panel. It
keeps a random `visitor_id` and the last `conversation_id` in `localStorage`.

---

## 11. Billing

Owner: backend-core. Without `STRIPE_SECRET_KEY` the server runs in demo mode:
checkout switches the plan instantly and the UI labels billing as a demo.

### `GET /billing/plans/` (public)

Not paginated, cheapest first.

```json
{"results": [Plan]}
```

### `GET /billing/subscription/` (agent)

`200` `Subscription`.

### `POST /billing/checkout/` (owner)

```json
{"plan": "pro"}
```

- **Demo mode**: switches the plan at once.
  `200` `{"mode": "demo", "checkout_url": null, "subscription": Subscription}`.
- **Stripe mode**: creates a Checkout Session for a paid plan.
  `200` `{"mode": "stripe", "checkout_url": "https://checkout.stripe.com/...", "subscription": Subscription}`
  (unchanged until the webhook arrives). Success and cancel return to
  `FRONTEND_URL/app/settings/billing?checkout=success` or `?checkout=cancelled`.

Errors:

| Status | Code | When |
| --- | --- | --- |
| 400 | `validation_error` | Unknown plan |
| 409 | `plan_unchanged` | Already on this plan |
| 409 | `plan_downgrade_blocked` | Current usage exceeds the target plan; `details` is `{"limit": "documents", "used": 40, "allowed": 10}` |
| 409 | `use_billing_portal` | Stripe mode, changing an existing paid subscription: use the portal |
| 503 | `service_unavailable` | Stripe unreachable |

### `POST /billing/portal/` (owner)

Stripe mode only. `200` `{"url": "https://billing.stripe.com/..."}`. Errors:
`409 billing_portal_unavailable` in demo mode or when the organisation has no Stripe
customer yet.

### `POST /billing/webhook/` (public, throttle `webhook`)

Stripe calls this with the raw event body and the `Stripe-Signature` header, verified
with `STRIPE_WEBHOOK_SECRET`. Handled: `checkout.session.completed`,
`customer.subscription.created`, `customer.subscription.updated`,
`customer.subscription.deleted`, `invoice.payment_failed`. Each event id is processed
once (`billing.StripeEvent`), so retries are safe. `200 {"received": true}`.
Errors: `400 invalid_signature`.

After any plan change the server publishes `subscription.updated` on
`ws/dashboard/`.

---

## 12. Analytics

Owner: backend-core. All endpoints need the agent role and take `date_from`,
`date_to` (see [Conventions](#filtering-search-and-ordering)) and optionally
`channel=widget|playground`. "Questions" are user messages; "answers" are assistant
messages.

### `GET /analytics/overview/`

```json
{
  "date_from": "2026-09-26",
  "date_to": "2026-10-25",
  "conversations": 412,
  "questions": 1036,
  "answered": 911,
  "not_found": 98,
  "refused": 3,
  "errors": 24,
  "answer_rate": 0.8793,
  "not_found_rate": 0.0946,
  "ratings": {"up": 140, "down": 22, "average": 0.7284, "satisfaction": 0.8642},
  "avg_latency_ms": 1840,
  "avg_first_token_ms": 410,
  "tickets_opened": 31,
  "cost_usd": "1.284500"
}
```

- `answer_rate` = `answered / questions`, `not_found_rate` = `not_found / questions`,
  both rounded to 4 places, `0` when there are no questions.
- `ratings.average`: mean of ratings on a -1 to 1 scale; `satisfaction` =
  `up / (up + down)`. Both `null` without ratings.
- `avg_latency_ms`, `avg_first_token_ms`: integers over answered messages, `null`
  without any.

### `GET /analytics/conversations-per-day/`

Every day in the range, zeros included, oldest first.

```json
{
  "date_from": "2026-09-26",
  "date_to": "2026-10-25",
  "results": [
    {"date": "2026-10-25", "conversations": 18, "questions": 41, "answered": 36, "not_found": 4}
  ]
}
```

### `GET /analytics/top-questions/?limit=10`

Questions grouped by their normalised text (lower case, punctuation stripped).
`limit`: 1 to 50, default 10.

```json
{
  "results": [
    {"question": "How long do refunds take?", "count": 37, "answered": 35, "not_found": 2, "last_asked_at": "2026-10-25T19:02:00Z"}
  ]
}
```

`question` is the most recent original wording in the group.

### `GET /analytics/top-documents/?limit=10`

Documents ranked by how many answers cited them.

```json
{
  "results": [
    {"document_id": "9e8f...", "title": "Refund policy", "citations": 88, "answers": 74}
  ]
}
```

`document_id` is `null` for documents deleted since (grouped by copied title).

### `GET /analytics/unanswered/` (paginated)

The content gap list: questions whose answer was `not_found`, newest first.

```json
{
  "count": 98,
  "next": null,
  "previous": null,
  "results": [
    {
      "message_id": "d2e3...",
      "conversation_id": "b7c8...",
      "question": "Do you ship to Iceland?",
      "channel": "widget",
      "asked_at": "2026-10-25T18:40:00Z",
      "top_similarity": 0.12,
      "has_ticket": true
    }
  ]
}
```

`message_id` is the user message. `top_similarity` may be `null`.

### `GET /analytics/costs/`

Token use and estimated cost by provider and model, from the usage recorded on each
assistant message and `LLM_PRICING_PER_MTOK` in settings. Local providers cost
`"0.000000"`.

```json
{
  "date_from": "2026-09-26",
  "date_to": "2026-10-25",
  "results": [
    {
      "provider": "claude",
      "model": "claude-opus-5-5",
      "messages": 210,
      "input_tokens": 402113,
      "output_tokens": 38122,
      "cache_read_input_tokens": 301220,
      "cache_creation_input_tokens": 12040,
      "cost_usd": "2.488400"
    }
  ],
  "total_cost_usd": "2.488400"
}
```

---

## 13. Websockets

### Framing

- Text frames only, each one JSON object with a string `type`.
- Either side may send `{"type": "ping"}`; the server answers `{"type": "pong"}`. The
  frontend pings every 25 seconds so proxies keep the socket open.
- Errors are frames, not closes, unless the socket cannot continue:

```json
{"type": "error", "code": "throttled", "message": "You are sending messages too fast.", "details": {"retry_after": 20}, "client_message_id": "c-17"}
```

`details` is always an object; `client_message_id` and `message_id` are present when
the error belongs to a specific question or answer.

Close codes:

| Code | Meaning |
| --- | --- |
| 4400 | Bad request (for example not JSON) and the socket cannot continue |
| 4401 | Not authenticated (no or bad `auth` frame) |
| 4403 | Origin not allowed (the handshake is rejected before accept) |
| 4404 | Unknown or disabled site key |
| 4408 | No `auth` frame within `WEBSOCKET_AUTH_TIMEOUT_SECONDS` (10) |
| 4429 | Too many connections from this IP |
| 1011 | Internal error |

### Dashboard authentication (`ws/dashboard/` and `ws/chat/`)

The `Origin` must be the dashboard (`CORS_ALLOWED_ORIGINS`). The token goes in the
first frame, not the URL, so it never reaches access logs:

```json
{"type": "auth", "token": "<access JWT>", "organization_id": "4f1e..."}
```

`organization_id` may be `null` (oldest membership). Server reply:

```json
{"type": "auth.ok", "user_id": "7b0c...", "organization_id": "4f1e...", "role": "owner"}
```

or an `error` frame with code `authentication_failed` followed by close 4401. Any
other frame before `auth` closes with 4401. When the access token later expires the
socket stays open; the client reconnects with a fresh token after its next refresh.

### `ws/dashboard/`

Owner: backend-core (`core.consumers.DashboardConsumer`). Read only: after `auth.ok`
the server pushes the events in [Real time events](#14-real-time-events) for the
authenticated organisation. The client sends only `ping`.

### `ws/chat/`

Owner: backend-ai (`assistant.consumers.ChatConsumer`). The dashboard playground.
Authenticate as above, then use the [chat frames](#chat-frames). Playground
conversations have `channel: "playground"` and `started_by` set to the user.

### `ws/widget/?site_key=<key>&visitor_id=<id>`

Owner: backend-core (`widget.consumers.WidgetConsumer`). The public website widget.

Handshake, in order:

1. `Origin` must be in the organisation's `allowed_origins` (localhost rule in DEBUG
   as for the public config). Otherwise the handshake is rejected (4403); the browser
   only sees a failed connection.
2. More than `WIDGET_CONNECTIONS_PER_MINUTE` (30) connections from this IP: accept,
   send `error` `throttled`, close 4429.
3. Unknown or disabled `site_key`: accept, send `error` `invalid_site_key`, close 4404.
4. `visitor_id` is optional: 16 to 64 characters of `[A-Za-z0-9_-]`. When missing or
   invalid the server makes one.

Then the server sends:

```json
{
  "type": "session.ready",
  "visitor_id": "v_5x9...",
  "organization_name": "Northwind Outfitters",
  "title": "Help",
  "greeting": "Hi! Ask me anything about our products and policies.",
  "brand_color": "#4f46e5",
  "position": "right"
}
```

No `auth` frame is used. Over `WIDGET_MESSAGES_PER_MINUTE` (20) `chat.message`
frames per minute per IP returns `error` `throttled` with `details.retry_after`; the
socket stays open. Besides the [chat frames](#chat-frames) the widget can send:

**Resume a conversation** (after a page reload):

```json
{"type": "conversation.resume", "conversation_id": "b7c8..."}
```

Reply, messages oldest first:

```json
{
  "type": "conversation.history",
  "conversation_id": "b7c8...",
  "status": "open",
  "messages": [
    {"id": "e3f4...", "role": "assistant", "content": "...", "answer_type": "answered", "rating": null, "citations": [Citation], "created_at": "2026-10-25T20:12:00Z"}
  ]
}
```

or `error` `not_found` when the conversation does not exist or belongs to another
visitor. The widget then starts fresh.

**Rate an answer**:

```json
{"type": "feedback", "message_id": "e3f4...", "rating": 1, "comment": ""}
```

Reply `{"type": "feedback.ok", "message_id": "e3f4...", "rating": 1}`.

### Chat frames

Shared by `ws/chat/` and `ws/widget/`. Owner of the frame shapes and of
`assistant.services.stream_answer`, which produces them: backend-ai. Both consumers
forward its frames unchanged.

**Ask a question** (client):

```json
{"type": "chat.message", "client_message_id": "c-17", "conversation_id": null, "content": "How long do refunds take?", "page_url": "https://shop.example.com/help"}
```

- `client_message_id`: required, client made, up to 64 characters; echoed back so the
  UI can match the answer to its optimistic bubble.
- `conversation_id`: `null` starts a new conversation; otherwise continue that one
  (must belong to this organisation, and on the widget to this visitor).
- `content`: 1 to `ASSISTANT_MAX_QUESTION_CHARS` (2000) characters after trimming.
- `page_url`: widget only, optional.

One answer streams at a time per socket. A `chat.message` while one is streaming gets
`error` `busy`.

**Answer stream** (server), always in this order for one question:

1. `message.start`

   ```json
   {"type": "message.start", "client_message_id": "c-17", "conversation_id": "b7c8...", "user_message_id": "d2e3...", "message_id": "e3f4...", "created_at": "2026-10-25T20:12:00Z"}
   ```

   `conversation_id` is the new id when the client sent `null`.

2. `message.delta`, zero or more:

   ```json
   {"type": "message.delta", "message_id": "e3f4...", "delta": "You can request a refund "}
   ```

   Concatenating every `delta` gives the answer text so far.

3. `message.citations`, once:

   ```json
   {"type": "message.citations", "message_id": "e3f4...", "citations": [Citation]}
   ```

   Only passages the answer actually cites, by marker. `[]` for `not_found`.

4. `message.done`, once:

   ```json
   {
     "type": "message.done",
     "message_id": "e3f4...",
     "conversation_id": "b7c8...",
     "status": "complete",
     "answer_type": "answered",
     "content": "You can request a refund within 30 days of delivery [1].",
     "provider": "ollama",
     "model": "llama3.2",
     "latency_ms": 2140,
     "first_token_ms": 380,
     "usage": Usage,
     "cost_usd": "0.000000",
     "offer_handoff": false
   }
   ```

   - `content` is the final text; the UI replaces the streamed text with it.
   - `offer_handoff` is `true` for `not_found`, `refused` and `error` answers, so the
     UI offers "Talk to a human".

If something fails after `message.start`, the server sends `error` with the
`message_id` and code `answer_failed` instead of the remaining frames, and the
assistant message is stored with `status: "failed"`. Failures before `message.start`
(for example `plan_limit_exceeded`, `validation_error`, `not_found` for a bad
`conversation_id`) are a single `error` frame with the `client_message_id`. When the
plan's monthly message limit is reached the error code is `plan_limit_exceeded` with
the same `details` as REST.

A provider failure is not an error frame: the pipeline falls back to the extractive
provider and the stream continues; `message.done.provider` shows who answered.

**Stop an answer** (client):

```json
{"type": "chat.cancel", "message_id": "e3f4..."}
```

The server stops generation and finishes with `message.done` and
`status: "truncated"`.

**Ask for a human** (client):

```json
{"type": "handoff.request", "conversation_id": "b7c8...", "email": "jo@example.net", "name": "Jo", "note": "I need to change my delivery address."}
```

`email` is required; `name` (up to 150) and `note` (up to 2000) are optional. Reply:

```json
{"type": "handoff.created", "ticket": {"id": "f9a0...", "conversation_id": "b7c8...", "status": "open", "created_at": "2026-10-25T20:15:00Z"}}
```

The conversation moves to `handed_off` and the dashboard gets `ticket.created`.

---

## 14. Real time events

Pushed on `ws/dashboard/` to every member of the organisation. Code anywhere in the
backend publishes them with `core.realtime.broadcast_org_event(organization_id,
event)` (sync, safe from worker threads and Celery) or `abroadcast_org_event`
(async). The event dict is the wire frame.

| Event | Publisher | Payload |
| --- | --- | --- |
| `document.status` | knowledge (backend-ai) | `{"type": "document.status", "document": Document}` on every status or chunk count change |
| `document.deleted` | knowledge (backend-ai) | `{"type": "document.deleted", "document_id": "9e8f..."}` |
| `conversation.created` | assistant (backend-ai) | `{"type": "conversation.created", "conversation": ConversationSummary}` |
| `conversation.updated` | assistant (backend-ai) | `{"type": "conversation.updated", "conversation": ConversationSummary}` after each answer or status change |
| `ticket.created` | assistant (backend-ai) | `{"type": "ticket.created", "ticket": Ticket}` |
| `ticket.updated` | assistant (backend-ai) | `{"type": "ticket.updated", "ticket": Ticket}` |
| `subscription.updated` | billing (backend-core) | `{"type": "subscription.updated", "subscription": Subscription}` |

Delivery is best effort. The dashboard treats events as hints and refetches lists on
reconnect.

---

## 15. Endpoint index

All REST paths are relative to `/api/v1`.

| Method | Path | Role | Owner |
| --- | --- | --- | --- |
| GET | `/health/` | public | backend-core |
| POST | `/auth/signup/` | public | backend-core |
| POST | `/auth/login/` | public | backend-core |
| POST | `/auth/refresh/` | public (cookie) | backend-core |
| POST | `/auth/logout/` | public (cookie) | backend-core |
| GET, PATCH | `/auth/me/` | any member | backend-core |
| POST | `/auth/password/` | any member | backend-core |
| GET | `/invitations/<token>/` | public | backend-core |
| POST | `/invitations/<token>/accept/` | public or signed in | backend-core |
| GET | `/organization/` | agent | backend-core |
| PATCH | `/organization/` | admin | backend-core |
| GET | `/organization/members/` | agent | backend-core |
| PATCH | `/organization/members/<id>/` | owner | backend-core |
| DELETE | `/organization/members/<id>/` | admin (self: any) | backend-core |
| GET, POST | `/organization/invitations/` | admin | backend-core |
| POST | `/organization/invitations/<id>/resend/` | admin | backend-core |
| DELETE | `/organization/invitations/<id>/` | admin | backend-core |
| GET | `/documents/` | agent | backend-ai |
| POST | `/documents/` | admin | backend-ai |
| GET | `/documents/tags/` | agent | backend-ai |
| GET | `/documents/<id>/` | agent | backend-ai |
| PATCH, DELETE | `/documents/<id>/` | admin | backend-ai |
| POST | `/documents/<id>/reindex/` | admin | backend-ai |
| GET | `/documents/<id>/text/` | agent | backend-ai |
| GET | `/documents/<id>/chunks/` | agent | backend-ai |
| GET | `/collections/` | agent | backend-ai |
| POST | `/collections/` | admin | backend-ai |
| PATCH, DELETE | `/collections/<id>/` | admin | backend-ai |
| GET | `/conversations/` | agent | backend-ai |
| GET, PATCH | `/conversations/<id>/` | agent | backend-ai |
| POST | `/messages/<id>/feedback/` | agent | backend-ai |
| GET | `/tickets/` | agent | backend-ai |
| GET, PATCH | `/tickets/<id>/` | agent | backend-ai |
| GET | `/assistant/providers/` | agent | backend-ai |
| POST | `/assistant/search/` | agent | backend-ai |
| GET | `/widget/config/` | agent | backend-core |
| PATCH | `/widget/config/` | admin | backend-core |
| POST | `/widget/config/rotate-key/` | admin | backend-core |
| GET | `/widget/public/config/` | public (origin checked) | backend-core |
| GET | `/billing/plans/` | public | backend-core |
| GET | `/billing/subscription/` | agent | backend-core |
| POST | `/billing/checkout/` | owner | backend-core |
| POST | `/billing/portal/` | owner | backend-core |
| POST | `/billing/webhook/` | public (Stripe signature) | backend-core |
| GET | `/analytics/overview/` | agent | backend-core |
| GET | `/analytics/conversations-per-day/` | agent | backend-core |
| GET | `/analytics/top-questions/` | agent | backend-core |
| GET | `/analytics/top-documents/` | agent | backend-core |
| GET | `/analytics/unanswered/` | agent | backend-core |
| GET | `/analytics/costs/` | agent | backend-core |

| Socket | Auth | Owner |
| --- | --- | --- |
| `ws/dashboard/` | `auth` frame, dashboard origin | backend-core |
| `ws/chat/` | `auth` frame, dashboard origin | backend-ai |
| `ws/widget/?site_key=&visitor_id=` | site key, allowed origin, IP rate limit | backend-core |
