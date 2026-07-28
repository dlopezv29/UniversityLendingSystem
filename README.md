# University Equipment Lending

A small, server-rendered CRUD web app that tracks equipment the **Universidad
Latina de Costa Rica** lends to its professors. Admins add/edit/remove/disable
items, manage professors, assign (request) items to a professor, and record
returns. Professors get a limited view of their own loans.

Everything runs on the Python standard library — no `pip install`. State lives
in a local SQLite database (`lending.db`), created automatically on first run.

## Tech

- **Pure Python standard library.** Modules used: `http.server`, `sqlite3`,
  `http.cookies`, `urllib.parse`, `secrets`, `hashlib`, `re`, `json`,
  `threading`, `datetime`.
- **Database: SQLite**, via the stdlib `sqlite3` module — a single file,
  `lending.db`, next to the source. Nothing to install and no server to start.
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

The first run creates `lending.db` and fills it with the demo data below. Every
later run reuses it, so items, professors, and loans survive restarts.

**To start over:** delete the file and run again.

```bash
rm lending.db && python3 app.py
```

Tests:

```bash
python3 -m unittest test_db -v
```

## Project layout

- `app.py` — entry point / server bootstrap.
- `db.py` — SQLite connection, schema, and seed data.
- `data.py` — data access (items, professors, accounts) + sessions and helpers.
- `handler.py` — HTTP request handler and all GET/POST route logic.
- `views.py` — HTML rendering (pages, modals, embedded CSS).
- `metrics.py` — in-process timing recorder behind the `/metrics` page.
- `loadtest.py` — concurrent load generator, for measuring under contention.
- `test_db.py` — tests for the data and metrics layers.

## Database

Three tables, created by `db.py` on first run:

| Table        | Holds                                                          |
|--------------|----------------------------------------------------------------|
| `professors` | `id` (autoincrement), `id_card` (unique), `name`, `department`  |
| `items`      | `id` (user-supplied, primary key), `name`, `category`, `description`, `status`, `assigned_to_id` → `professors.id`, `assigned_on`, `due_date` |
| `users`      | `username` (primary key), `password`, `role`, `professor_id` → `professors.id` |

Constraints do real work here: `id_card` and item `id` uniqueness is enforced by
the engine (not by a Python check two threads could both pass), `CHECK` clauses
reject invalid `status`/`role` values, and `ON DELETE RESTRICT` stops a
professor being deleted while they still hold items.

A loan points at a professor by **id**, but `data.py` joins that back to the
professor's name and exposes it as `item["assigned_to"]`. Renaming a professor
therefore updates all of their loans automatically.

Sessions stay in an in-memory dict on purpose — logging in again after a restart
is intended, so tokens are not persisted. Categories are a fixed list in
`data.CATEGORIES`, not a table.

## Performance measurement

Sign in as `admin` and open **http://localhost:8000/metrics** (the *Performance*
tab). Everything is measured in-process by `metrics.py` and kept in memory, so
the numbers cover the time since the server started or since you last pressed
**Reset**.

Three layers are timed, which is what makes the page useful — you can see where
a request's time actually goes:

| Layer | What it measures | Where it is recorded |
|-------|------------------|----------------------|
| **HTTP requests** | Whole request: database work **plus** HTML rendering | `do_GET` / `do_POST` in `handler.py` |
| **Data functions** | One `data.py` call, including the SQL it runs | `@metrics.timed("function")` decorator |
| **SQL statements** | Just executing the statement | `query` / `query_one` / `execute` in `db.py` |

Two extra numbers are specific to how this app is built:

- **DB connection open** — how long `sqlite3.connect` takes. It happens once,
  on first use, not per request.
- **Lock wait** — how long a thread waited for `db._lock` before its statement
  could run. Every query shares one connection, so this is the contention cost.

### Measuring under load

Lock wait sits near zero while requests arrive one at a time. To make threads
actually queue, run the load generator against a live server:

```bash
python3 app.py                      # terminal 1
python3 loadtest.py -c 20 -n 400    # terminal 2
```

`-c` is concurrent threads, `-n` total requests. It signs in, hammers `/` and
`/professors`, and prints client-side latency; open `/metrics` afterwards for the
server-side breakdown.

### Reading the results

A representative run (400 requests, 20 threads, on a laptop):

```
Statement           Calls   Mean ms   p95 ms
_lock wait           1203      1.62     4.37
SELECT users          403     0.049    0.210
SELECT items          400     0.047    0.196
SELECT professors     400     0.046    0.204
```

SQLite executes a statement in ~0.05 ms. `find_user` measured 2.42 ms mean over
the same run — so **the query is not the cost, waiting for the lock is**, and
under concurrency it accounts for roughly 98% of the time attributed to a data
function. That is the direct consequence of one serialized connection, and it is
the number that would improve by moving to a connection pool or a client/server
database. Compare it against `GET /` (5.88 ms mean) to see how much of a page
load is rendering rather than data access.

Two caveats when reading the tables:

- The layers **nest**. A route's time contains its data functions, which contain
  their SQL and their lock wait — so the columns do not sum to a total, they
  decompose one.
- **Client-side and server-side maxima disagree under heavy load, and that is
  expected.** At `-c 30`, `loadtest.py` reported a 1006 ms worst case while the
  server's own worst `GET /` was 29 ms. The missing second was spent in the TCP
  accept queue: `ThreadingHTTPServer` inherits `request_queue_size = 5`, so
  connections beyond that wait before the handler ever starts and the in-process
  timer ever runs. Compare *means* across the two, not maxima, and raise
  `Handler`'s queue size if you want to measure past that ceiling.

## Accounts

Two demo accounts, seeded into the `users` table on first run:

| Username  | Password   | Role        | Notes                                              |
|-----------|------------|-------------|----------------------------------------------------|
| `admin`   | `password` | `admin`     | Full access to everything.                         |
| `DGarcia` | `password` | `professor` | Bound to professor **Prof. García**; limited view. |

> Passwords are stored **in plaintext** in the `users` table — so anyone who
> opens `lending.db` can read every password. Demo auth only, not for real use.
> `lending.db` is gitignored for this reason. See
> [Quirks](#quirks--important-notes).

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
| Performance page (`/metrics`)                |  ✅   |    ❌ (redirects to `/`) |

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
| `/metrics`    | admin  | Performance page — timings per route, per `data.py` function, and per SQL statement. |

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
| `/metrics/reset`      | admin  | Clear all collected timings and restart the measurement clock. |

Admin-only POST routes are enforced by the `admin_routes` tuple in
`handler.py`; a non-admin hitting one redirects to `/`.

## Data model

All state lives in SQLite. `data.py` returns rows as plain dicts in the shapes
below, so the rendering layer never sees SQL.

**Item** (`data.all_items()`, `data.find_item(id)` — dicts):

| Field         | Meaning |
|---------------|---------|
| `id`          | Caller-supplied unique string ID. |
| `name`        | Display name. |
| `category`    | One of `data.CATEGORIES`. |
| `description` | Free text. |
| `status`      | `available` \| `assigned` \| `disabled`. |
| `assigned_to` | Professor name, joined from `assigned_to_id` (empty if not assigned). |
| `assigned_on` | ISO date the loan started. |
| `due_date`    | ISO return date. |

**Professor** (`data.all_professors()` — dicts): `id` (int, `AUTOINCREMENT`),
`id_card` (unique string), `name`, `department`.

**Accounts & sessions:** `data.find_user(username)` →
`{name, password, role, professor}`, where `professor` is the linked
professor's name (empty for admins), resolved through the `professor_id`
foreign key. On login a random token (`session=<token>` cookie, `HttpOnly`,
`SameSite=Lax`) is stored in `data.SESSIONS[token] = username` — in memory, so
it does not survive a restart.

**Categories:** `Monitors`, `Peripherals`, `Keys`, `Controls`.

## Module & function reference

### `app.py`

- `main()` — calls `db.init()`, builds a `ThreadingHTTPServer` on
  `localhost:8000` with `Handler`, serves forever, and shuts down cleanly on
  `Ctrl+C`.

### `db.py`

The only module that imports `sqlite3`. Holds one connection opened with
`check_same_thread=False` and serialized behind a `threading.Lock`, because
`ThreadingHTTPServer` runs a thread per request. `PRAGMA foreign_keys = ON` is
set on connect — SQLite ignores foreign keys otherwise.

- `DB_PATH`, `SCHEMA` — the database file path and the `CREATE TABLE` script.
- `init()` — creates the schema if missing, seeds a brand-new database.
- `connect()` / `close()` — shared connection lifecycle.
- `query(sql, params)` / `query_one(sql, params)` — SELECT helpers returning
  `sqlite3.Row`.
- `execute(sql, params)` — INSERT/UPDATE/DELETE plus commit; raises
  `sqlite3.IntegrityError` when a constraint rejects the write.
- `_label(sql)` — turns a statement into a short metric name like
  `SELECT users`, cached per SQL string.

All three statement helpers time the lock wait and the execution separately and
report them to `metrics`.

### `metrics.py`

In-memory timing recorder. No dependencies on the rest of the app, so nothing
imports it in a cycle. Keeps at most 2000 recent samples per name (a bounded
`deque`), which is enough for percentiles without growing forever.

- `record(group, name, seconds)` — add one sample; group is `request`,
  `function`, or `query`.
- `timed(group, name=None)` — decorator recording how long a function takes,
  including when it raises.
- `record_connection(seconds)` — time of one `sqlite3.connect`.
- `wait_start()` / `wait_end(start)` — bracket acquiring `db._lock`; records the
  wait as the `_lock wait` series and tracks peak concurrent waiters.
- `snapshot()` — consistent copy of everything, durations in milliseconds, with
  count/mean/min/p50/p95/p99/max/total per name.
- `reset()` — drop all samples and restart the clock.

### `loadtest.py`

Standalone script (not imported by the app). Signs in, then fires `-n` requests
across `-c` threads at `/` and `/professors`, printing client-side latency
percentiles and throughput. Use it to create the concurrency that makes
`_lock wait` visible on `/metrics`.

### `data.py`

Module state: `SESSIONS` (in memory), `CATEGORIES`, `_CODE_WORDS`. Everything
else is a query.

Helpers:
- `new_token()` → random 32-char hex session token.
- `generate_return_code()` → cosmetic pickup code like `BRAVO-TANGO-4821` (two
  words from `_CODE_WORDS` + a 4-digit number).
- `valid_item_id(item_id)` → `True` if it matches `[A-Za-z0-9_-]+` (non-empty).
- `valid_id_card(id_card)` → same rule as `valid_item_id`.
- `is_overdue(item)` → `True` if assigned and `due_date` is before today.

Items:
- `all_items()` / `available_items()` → lists of item dicts.
- `find_item(item_id)` → item dict or `None`.
- `find_available_item_by_name(name)` → first available item with that name.
- `add_item(item_id, name, category, description)` → the new item dict, or
  `None` if the id is taken.
- `update_item(item_id, name, category, description)` — blank name and unknown
  category are left unchanged.
- `delete_item(item_id)`, `set_item_status(item_id, status)`.
- `assign_item(item_id, professor_id, assigned_on, due_date)` — lends an item.
- `return_item(item_id)` — clears assignee and both dates in one statement.

Professors:
- `all_professors()`, `find_professor(prof_id)`,
  `find_professor_by_id_card(id_card)`, `find_professor_by_name(name)`.
- `add_professor(name, department, id_card)` → the new dict, or `None` if the
  ID Card is taken.
- `update_professor(prof_id, id_card, name, department)` → `False` if the ID
  Card belongs to someone else.
- `delete_professor(prof_id)` → `False` if the database refuses because they
  still hold items.
- `items_assigned_to(professor_id)`, `professor_active_item_count(professor_id)`.

Accounts:
- `find_user(username)` → `{name, password, role, professor}` or `None`.

### `handler.py`

`Handler(BaseHTTPRequestHandler)` — one class handling all routing.

Helpers:
- `_send_html(code, body)` — writes an HTML response with proper headers.
- `_redirect(location, cookie=None)` — 303 redirect, optionally setting a cookie.
- `_read_form()` — parses a URL-encoded POST body into a flat `dict`.
- `current_user()` — resolves the `session` cookie to `{name, role, professor}`
  or `None`.
- `log_message(...)` — overridden to silence the default console logging.
- `_metric_label(verb)` — `"GET /"`-style metric name; paths outside
  `KNOWN_PATHS` collapse to `other` so 404 floods cannot grow the metrics table.

Routers:
- `do_GET()` / `do_POST()` — time the whole request, then delegate to
  `_route_get()` / `_route_post()`.
- `_route_get()` — gates on auth, then serves `/login`, `/`, `/professors`,
  `/metrics`, or 404.
- `_route_post()` — handles `/login`, `/logout`, then auth- and admin-gates the
  mutation routes (`/add`, `/edit`, `/remove`, `/toggle-disable`, `/return`,
  `/request`, `/professors/*`, `/metrics/reset`), running per-route validation
  before mutating `data`.

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
- `render_metrics_page(user, snap)` — the Performance page: KPI cards plus one
  stats table per layer, from a `metrics.snapshot()`.
- `_ms(value)` / `_metric_table(rows, label)` — millisecond formatting and the
  shared stats-table markup.
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

## Metrics & observability

The latency metrics below are **collected today** — see
[Performance measurement](#performance-measurement) and the `/metrics` page. The
reliability and product metrics are not; they are what you'd want to instrument
**before/when going to production**.

### Performance / latency — built
- **Response time** — per-route latency (mean / p50 / p95 / p99 / max), measured
  around `do_GET` / `do_POST` in `handler.py`. Watch `/` (renders the full items
  table) and `/professors` (renders a card grid) since render cost grows with
  item and professor counts.
- **Execution time of hot paths** — time in each `data.py` function and each SQL
  statement, reported separately. The statements are indexed lookups taking
  ~0.05 ms; the visible cost is `_lock wait`, because everything serializes
  behind `db._lock`. That is the first thing that degrades at scale.
- **Connection cost** — time to open the SQLite connection, one-off at startup.
- **Throughput** — requests/sec and concurrent sessions the
  `ThreadingHTTPServer` sustains before latency degrades. Measured client-side by
  `loadtest.py`; peak concurrent waiters appear on `/metrics`.

### Reliability / errors — not built
- **Error count & rate** — HTTP 5xx (unhandled exceptions in a handler) and 4xx
  (404s from `render_404`, redirects from failed auth). Track as a rate
  (errors / total requests), not just a raw number.
- **Failed logins** — count of `/login` attempts that redirect to
  `/login?error=1` (useful for both UX and abuse detection).
- **Validation rejections** — how often `/add`, `/request`, `/professors/*`
  bounce on the validation rules (duplicate ID, bad date, etc.).
- **Uptime / availability** — server up %, plus mean time to recovery after a
  restart (items and professors survive; sessions do not, so everyone
  re-authenticates).

### Product / usage — not built
- **User satisfaction** — e.g. a CSAT/NPS prompt after a return, or a simple
  thumbs-up/down on the receipt page (`render_return_result`).
- **Loan activity** — requests created, returns completed, average loan
  duration, and **overdue rate** (share of assigned items past `due_date` via
  `is_overdue`).
- **Utilization** — % of items `available` vs `assigned` vs `disabled`, and how
  many professors are at/over the 3-item soft limit.
- **Active users / sessions** — daily active users and live session count
  (`len(data.SESSIONS)`).

### How you'd collect the rest
- Extend the existing `do_GET` / `do_POST` timing wrapper to also record status
  codes, giving error rate alongside latency.
- Export `metrics.snapshot()` as JSON for Prometheus/Grafana instead of only
  rendering it, plus structured request logs (currently `log_message` is
  silenced) for error/usage analysis.
- Record loan events in their own table (the current schema keeps only the
  *current* state of each item) so product metrics like overdue rate and loan
  duration are queryable over time.

## Quirks / important notes

- **Data persists; sessions do not.** Items, professors, and accounts live in
  `lending.db` and survive restarts. Session tokens are an in-memory dict, so
  everyone signs in again after a restart. Delete `lending.db` to reset to the
  seed data.
- **Metrics are in-memory and per-process.** `/metrics` resets to empty on every
  restart, and only the last 2000 samples per name feed the percentiles. The
  instrumentation itself is a few `perf_counter()` calls per query — negligible
  next to the lock wait it measures, but it is always on.
- **No migrations.** `db.init()` only runs `CREATE TABLE IF NOT EXISTS`. Editing
  `SCHEMA` will not alter an existing `lending.db` — delete the file and let it
  be recreated.
- **Auth is demo-grade.** Passwords are plaintext in the `users` table, readable
  by anyone who opens the database file (which is why it is gitignored).
  Sessions are a plain in-memory dict. Do not use as-is for anything real.
- **Return code `1234` is hardcoded** in `handler.py` (`/return`). Admins bypass
  it entirely; only professors are prompted for it.
- **The receipt QR is a placeholder** (`_qr_placeholder_svg`) — it is not a
  scannable QR code. The generated pickup code (`generate_return_code`) is
  cosmetic and unrelated to the `1234` entry code.
- **The `DGarcia` account is bound to a fixed display name** (`Prof. García`).
  Renaming or removing that professor in the UI does not update the login
  binding.
- **Google Fonts is loaded over the network** for the Inter typeface.

---

# Production blueprint (if deployed for real)

Everything above describes the **current demo**. This section is a parallel
version of the same document for a **real, deployed** app — same headings, but
describing how each piece would change once it runs on a server with a real
database, real QR codes, live updates, and hardening. It's a target design, not
what's built today.

## Tech (production)

- **Web framework instead of raw `http.server`** — e.g. FastAPI or Flask behind
  a real WSGI/ASGI server (Gunicorn/Uvicorn), fronted by Nginx as a reverse
  proxy with TLS. `ThreadingHTTPServer` is replaced.
- **Client/server database** — PostgreSQL (or MySQL) for items, professors,
  loans, and users, accessed via an ORM (SQLAlchemy) or query layer, with schema
  migrations (Alembic) instead of the current create-if-missing `db.init()`. The
  table shapes carry over from SQLite; what changes is concurrent writers,
  connection pooling, and managed backups.
- **Session/cache store** — Redis for sessions (replacing the in-memory
  `data.SESSIONS` dict) and for caching hot reads.
- **Real QR generation** — a proper QR library (e.g. `qrcode` / `segno`)
  producing scannable codes, replacing the decorative `_qr_placeholder_svg`. The
  QR encodes a real return/pickup URL or token, not a cosmetic pattern.
- **Live updates** — WebSockets or Server-Sent Events so the items table and
  professor cards update in real time across clients (no manual refresh);
  optionally a small frontend (React/HTMX) instead of full-page re-renders.
- **Self-hosted assets** — bundle the Inter font locally (no Google Fonts
  network dependency).
- **Containerized + orchestrated** — Docker images deployed to a cloud
  (Kubernetes / ECS / a PaaS), not `python3 app.py` on localhost.

## Run / Deploy (production)

- **Not localhost.** Runs on a public host behind a domain + HTTPS, e.g.
  `https://lending.ulatina.ac.cr`.
- Container build → CI pipeline → deploy. Config via environment variables
  (DB URL, secret keys, Redis URL) — nothing hardcoded.
- **Live updates / zero-downtime deploys** — rolling or blue-green deploys so
  new versions ship without dropping sessions (sessions live in Redis, so a
  restart no longer wipes login state).
- Managed database with automated backups + point-in-time recovery.

## Accounts (production)

- Users stored in the database, **passwords hashed** (bcrypt/argon2) — never
  plaintext.
- Real onboarding: an admin invites/creates users; professors get their own
  login instead of a hardcoded `DGarcia` account bound to a fixed name.
- Integration with the university's **SSO / LDAP / OAuth** so staff use existing
  credentials. Password reset, email verification, account lockout.

## Roles & permissions (production)

- Same core roles (`admin`, `professor`) but backed by a real
  **authorization layer** (role-based access control), possibly more roles
  (e.g. `department-admin`, `auditor`).
- Server-side enforcement on every route (as today) **plus** audit logging of
  who did what and when.
- The professor↔account binding comes from the DB relationship, so renaming a
  professor updates everywhere (fixes the current `DGarcia` quirk).

## Features (production)

Everything the demo does, plus:

- **Real return codes / QR** — scannable QR on the receipt; scanning it (or
  entering the code) verifies against the DB, so codes aren't hardcoded.
- **Notifications** — email/SMS reminders before a due date and when an item is
  overdue.
- **Live dashboard** — real-time item availability and overdue counts via
  WebSockets/SSE.
- **Search & pagination** — server-side across large catalogs (the current
  client-side filtering doesn't scale).
- **Audit trail & history** — full loan history per item and per professor.
- **File uploads** — item photos, condition reports.
- **Configurable limits** — the 3-item soft limit becomes an admin setting, not
  a constant in code.
- **Reporting / export** — CSV/PDF exports for inventory and overdue reports.

## Routes reference (production)

- Same logical routes, but exposed as a **versioned REST/JSON API**
  (`/api/v1/items`, `/api/v1/professors`, `/api/v1/loans`, `/api/v1/auth/...`)
  consumed by a frontend, **plus** a WebSocket/SSE endpoint for live updates.
- Proper HTTP semantics (POST/PUT/PATCH/DELETE, not POST-only), rate limiting,
  CSRF protection, and input validation at the API boundary.

## Data model (production)

- Normalized relational tables: `users`, `items`, `professors`, `loans`
  (a loan row per assignment, so history is preserved instead of overwriting the
  item's `assigned_to` / `due_date` fields), `categories` as its own table.
- Foreign keys, indexes on lookup columns (item id, id_card), timestamps
  (`created_at` / `updated_at`), soft-delete flags.
- Sessions/tokens in Redis with expiry, not a plain dict.

## Module & function reference (production)

- The current split (`data` / `handler` / `views`) becomes layered:
  **models** (ORM), **repository/service** layer (business rules like the 3-item
  limit and validation), **API/controllers** (routing), and **templates or a
  separate frontend** for rendering.
- Helpers like `find_item` / `find_professor` become indexed DB queries;
  `is_overdue` becomes a DB-computed field or query filter; `generate_return_code`
  ties to a persisted, verifiable token; `_qr_placeholder_svg` is replaced by a
  real QR encoder.

## Validation rules (production)

- Same rules, enforced at the API layer **and** the database (unique
  constraints, check constraints, NOT NULL) so bad data can't slip in from
  another client.
- Stronger input validation/sanitization, size limits, and rate limiting to
  resist abuse.

## Metrics & observability (production)

Now actually collected, not hypothetical. Same categories as above, wired to
real tooling:

### Performance / latency (production)
- Response time p50/p95/p99 **per API endpoint**, exported to Prometheus and
  graphed in Grafana; alerts on p95 regressions.
- Database query timing (slow-query log), cache hit rate (Redis), and
  end-to-end request tracing (OpenTelemetry).

### Reliability / errors (production)
- Error rate (5xx/4xx) with alerting; exceptions captured in Sentry (or similar)
  with stack traces.
- Uptime/availability SLOs, health-check endpoints, and on-call alerting.
- Failed-login and abuse metrics feeding security monitoring.

### Product / usage (production)
- **User satisfaction** collected for real (in-app CSAT/NPS, support tickets).
- Loan throughput, average loan duration, **overdue rate**, item utilization,
  DAU/MAU — all queryable from the `loans` table over time.
- Funnel/adoption analytics (e.g. how often requests are created vs abandoned).

### How they're collected (production)
- Metrics middleware on every request → Prometheus/Grafana.
- Structured JSON logs (the demo's silenced `log_message` becomes real request
  logging) shipped to a log aggregator (ELK/Loki).
- Errors → Sentry; traces → OpenTelemetry; product events → an analytics
  pipeline/warehouse.

## Quirks / important notes (production)

The demo's quirks are **resolved** in this version:

- Data **is** persisted (real DB + backups) — restarts no longer wipe state.
- Auth is real — hashed passwords, SSO, session expiry.
- Return codes/QR are **real and verifiable**, not hardcoded `1234` or a
  decorative SVG.
- The professor↔account binding lives in the DB, so renames propagate.
- Fonts and other assets are self-hosted (no third-party network dependency).
- New production concerns to watch instead: DB migrations, secret management,
  scaling/load, GDPR/data-retention, and dependency/security patching.
