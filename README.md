# University Equipment Lending

A small, server-rendered CRUD web app that tracks equipment the **Universidad
Latina de Costa Rica** lends to its professors. Admins add/edit/remove/disable
items, manage professors, assign (request) items to a professor, and record
returns. Professors get a limited view of their own loans.

Everything runs on the Python standard library — no database, no `pip install`.

## Tech

- **Pure Python standard library.** Modules used: `http.server`,
  `http.cookies`, `urllib.parse`, `secrets`, `hashlib`, `re`, `json`,
  `datetime`.
- Server: `ThreadingHTTPServer` on `http://localhost:8000`.
- Frontend: server-rendered HTML with embedded CSS (no build step, no JS
  framework — just a little inline vanilla JS for modals/filters).
- **Only external dependency:** the page loads the *Inter* font from Google
  Fonts over the network. Offline, the browser falls back to system fonts; the
  app still works.

## Run

```bash
python3 app.py
```

Open **http://localhost:8000** and sign in. Stop with `Ctrl+C`.

## Project layout

- `app.py` — entry point / server bootstrap.
- `data.py` — in-memory state (items, professors, accounts, sessions) + helpers.
- `handler.py` — HTTP request handler and all GET/POST route logic.
- `views.py` — HTML rendering (pages, modals, embedded CSS).

## Accounts

Two demo accounts (from `data.USERS`, in-memory, reset on restart):

| Username  | Password   | Role        | Notes                                              |
|-----------|------------|-------------|----------------------------------------------------|
| `admin`   | `password` | `admin`     | Full access to everything.                         |
| `DGarcia` | `password` | `professor` | Bound to professor **Prof. García**; limited view. |

> Passwords are stored **in plaintext, in memory** — demo auth only, not for
> real use. See [Quirks](#quirks--important-notes).

## Roles & permissions

There are exactly two roles: `admin` and `professor`.

| Capability                                   | admin | professor |
|----------------------------------------------|:-----:|:---------:|
| View items table + filters                   |  ✅   |    ✅     |
| "Assigned to me" filter                      |  —    |    ✅ (pre-checked) |
| Add / edit / remove / disable items          |  ✅   |    ❌     |
| Create a new request (assign to professor)   |  ✅   |    ❌     |
| Return an item                               |  ✅ (direct, no code) | ✅ (must enter code `1234`) |
| Professors page + management (`/professors`) |  ✅   |    ❌ (redirects to `/`) |

A professor only sees the items table. Their return goes through a **return-code
modal** that requires the code `1234`; an admin returns an item directly with no
code.

## Features

- **Items table** with per-item status (`available` / `assigned` / `disabled`),
  category, and who each item is assigned to (with an **Overdue** badge past the
  due date).
- **Filters:**
  - *Category* and *Overdue* — server-side, via GET query params on `/`.
  - *Item name* and *Assigned to me* — client-side (inline JS row filtering).
- **Add / edit item** (admin) — caller-supplied **ID**, name, fixed **category**
  (Monitors, Peripherals, Keys, Controls), description.
- **Disable / enable item** (admin) — only togglable while the item is
  `available` or `disabled` (not while `assigned`).
- **Remove item** (admin; confirm prompt).
- **Professor management** (admin) — card-grid view (`/professors`) showing each
  professor, their ID Card, department, and active-item count; add / edit /
  remove. A professor can't be removed while they have active assigned items.
- **New request** (admin) — assign an available item to a professor via
  type-to-filter datalists, with a return date (must be today or later).
  If the professor already has **≥3 active items**, a **confirmation page**
  lists their current items (flagging overdue ones) before assigning a 4th+.
- **Return** — marks the item available again and shows a **receipt page** with a
  decorative QR placeholder and a randomly generated pickup code
  (e.g. `BRAVO-TANGO-4821`).

## Routes reference

All routes live in `handler.py`. Unauthenticated requests redirect to `/login`.

### GET

| Path          | Access | Description |
|---------------|--------|-------------|
| `/login`      | public | Login page (`?error=1` shows invalid-credentials message). |
| `/`           | any signed-in | Item Management page. Query: `category` (must be a known category), `overdue=1`. |
| `/professors` | admin  | Professors Management page. Non-admins redirect to `/`. |

### POST

| Path                  | Access | Description |
|-----------------------|--------|-------------|
| `/login`              | public | Validates credentials, sets `session` cookie, redirects `/`. |
| `/logout`             | any    | Clears the session + cookie, redirects `/login`. |
| `/add`                | admin  | Add an item (validates ID: required, well-formed, unique). |
| `/edit`               | admin  | Edit an item's name/category/description. |
| `/remove`             | admin  | Remove an item. |
| `/toggle-disable`     | admin  | Toggle `available` ⇄ `disabled`. |
| `/return`             | admin + professor | Return an item. Professor must send `code=1234`; admin bypasses. Renders the receipt. |
| `/request`            | admin  | Assign an item to a professor; enforces date + ≥3-item confirmation. |
| `/professors/add`     | admin  | Add a professor (validates ID Card: required, well-formed, unique). |
| `/professors/edit`    | admin  | Edit a professor (re-validates ID Card uniqueness). |
| `/professors/remove`  | admin  | Remove a professor (blocked if they have active items). |

Admin-only POST routes are enforced by the `admin_routes` tuple in
`handler.py`; a non-admin hitting one redirects to `/`.

## Data model

All state is defined in `data.py` and mutated in place (no persistence).

**Item** (`data.ITEMS` — list of dicts):

| Field         | Meaning |
|---------------|---------|
| `id`          | Caller-supplied unique string ID. |
| `name`        | Display name. |
| `category`    | One of `data.CATEGORIES`. |
| `description` | Free text. |
| `status`      | `available` \| `assigned` \| `disabled`. |
| `assigned_to` | Professor name (empty if not assigned). |
| `assigned_on` | ISO date the loan started. |
| `due_date`    | ISO return date. |

**Professor** (`data.PROFESSORS` — list of dicts): `id` (int, auto-increment via
`data.NEXT_PROF_ID`), `id_card` (unique string), `name`, `department`.

**Accounts & sessions:** `data.USERS[username] = {password, role, professor?}`
(the `professor` key maps the `DGarcia` account to a display name). On login a
random token (`session=<token>` cookie, `HttpOnly`, `SameSite=Lax`) is stored in
`data.SESSIONS[token] = username`.

**Categories:** `Monitors`, `Peripherals`, `Keys`, `Controls`.

## Module & function reference

### `app.py`

- `main()` — builds a `ThreadingHTTPServer` on `localhost:8000` with `Handler`,
  serves forever, and shuts down cleanly on `Ctrl+C`.

### `data.py`

Module state: `USERS`, `SESSIONS`, `CATEGORIES`, `ITEMS`, `PROFESSORS`,
`NEXT_PROF_ID`, `_CODE_WORDS`.

- `new_token()` → random 32-char hex session token.
- `generate_return_code()` → cosmetic pickup code like `BRAVO-TANGO-4821` (two
  words from `_CODE_WORDS` + a 4-digit number).
- `find_item(item_id)` → item dict or `None`.
- `valid_item_id(item_id)` → `True` if it matches `[A-Za-z0-9_-]+` (non-empty).
- `find_professor(prof_id)` → professor dict by int id, or `None`.
- `find_professor_by_id_card(id_card)` → professor dict by ID Card, or `None`.
- `valid_id_card(id_card)` → same rule as `valid_item_id`.
- `is_overdue(item)` → `True` if assigned and `due_date` is before today.
- `add_item(item_id, name, category, description)` → appends an `available` item.
- `add_professor(name, department, id_card)` → appends a professor, bumps
  `NEXT_PROF_ID`.

### `handler.py`

`Handler(BaseHTTPRequestHandler)` — one class handling all routing.

Helpers:
- `_send_html(code, body)` — writes an HTML response with proper headers.
- `_redirect(location, cookie=None)` — 303 redirect, optionally setting a cookie.
- `_read_form()` — parses a URL-encoded POST body into a flat `dict`.
- `current_user()` — resolves the `session` cookie to `{name, role, professor}`
  or `None`.
- `log_message(...)` — overridden to silence the default console logging.

Routers:
- `do_GET()` — gates on auth, then serves `/login`, `/`, `/professors`, or 404.
- `do_POST()` — handles `/login`, `/logout`, then auth- and admin-gates the
  mutation routes (`/add`, `/edit`, `/remove`, `/toggle-disable`, `/return`,
  `/request`, `/professors/*`), running per-route validation before mutating
  `data`.

### `views.py`

Every function returns an HTML string; state is read live from the `data` module.

- `render_layout(title, body, user=None, active_nav="")` — shared HTML shell:
  header, brand, user bar, admin section nav, and all embedded CSS.
- `render_index(user, ...)` — Item Management page: table, filters, and (admin)
  add/edit/request modals or (professor) the return-code modal. Also carries
  inline error/values back into the relevant modal after a failed submit.
- `_initials(name)` — two-letter avatar initials, ignoring honorifics.
- `render_professors_page(user, ...)` — professor card grid with active-item
  counts, add form, and edit modal.
- `render_confirm_request(item, professor_name, due_date, current_items, user)`
  — the ≥3-item confirmation page.
- `_qr_placeholder_svg(code)` — builds a **decorative** QR-looking SVG from an
  MD5 hash of the code (not a scannable QR).
- `render_return_result(item, code, user)` — the return receipt (QR placeholder
  + pickup code).
- `render_row(item, user)` — one item table row, with role-appropriate actions.
- `render_login(error=False)` — the sign-in page.
- `render_404()` — the not-found page.

## Validation rules

- **Item ID** and **professor ID Card**: must be non-empty, match
  `[A-Za-z0-9_-]+`, and be unique (`valid_item_id` / `valid_id_card`).
- **Return date**: must be today or later (`/request`).
- **Category**: an edit/add only applies a category if it is in `data.CATEGORIES`.
- **Professor removal**: blocked while the professor has active assigned items.

## Quirks / important notes

- **Data is not persisted.** All state lives in memory; stopping or restarting
  the server resets everything to the built-in sample items and accounts. This
  is by design (no database).
- **Auth is demo-grade.** Passwords are plaintext in `data.USERS`; sessions are a
  plain in-memory dict. Do not use as-is for anything real.
- **Return code `1234` is hardcoded** in `handler.py` (`/return`). Admins bypass
  it entirely; only professors are prompted for it.
- **The receipt QR is a placeholder** (`_qr_placeholder_svg`) — it is not a
  scannable QR code. The generated pickup code (`generate_return_code`) is
  cosmetic and unrelated to the `1234` entry code.
- **The `DGarcia` account is bound to a fixed display name** (`Prof. García`).
  Renaming or removing that professor in the UI does not update the login
  binding.
- **Google Fonts is loaded over the network** for the Inter typeface.
