# University Equipment Lending

A tiny CRUD web app to track items the university lends to professors.
Add, edit, remove, disable items, and request / return them.

## Tech
- Pure Python **standard library** — no database, no `pip install`.
- Runs on `http.server` at `http://localhost:8000`.
- Server-rendered HTML frontend.

## Project layout
- `app.py` — entry point: server bootstrap (`python3 app.py`).
- `handler.py` — HTTP request handler and all route logic.
- `views.py` — HTML rendering (pages, modals, embedded CSS).
- `data.py` — hardcoded state (items, professors, accounts) + helpers.

## Run

```bash
python3 app.py
```

Then open **http://localhost:8000** in your browser.
Stop with `Ctrl+C`.

## Login

The app is gated by a login. Two demo accounts (in-memory, reset on restart):

| Username | Password   | Can do                                                        |
|----------|------------|-----------------------------------------------------------------|
| `admin`  | `password` | Everything: add, edit, remove, disable, manage professors, request, return, view |
| `staff`  | `staff`    | View items + who's assigned; return only                        |

Sessions are stored in memory (cookie-based) and reset when the server restarts.

## Features
- **Add / edit** an item (admin only) — name, fixed **category**
  (Monitors, Peripherals, Keys, Controls), description.
- **Disable / enable** an item (admin only) — disabled items are hidden from
  the New Request item picker; only togglable while the item is available.
- **Remove** an item (admin only; confirm prompt).
- **Manage professors** (admin only) — add / edit / remove professors; a
  professor can't be removed while they have active items.
- **New request**: assign an available item to a professor (admin only) via
  type-to-filter dropdowns, with a return date. Validates the professor
  won't silently exceed 3 active items — a 4th+ request shows a confirmation
  page listing their current items (flagging any overdue) before proceeding.
- **Return** an assigned item (admin + staff; marks it available again).
- **Filter** the items table by category and by overdue-only.
- **View** the items table with description, category, and who each item is
  assigned to (with an overdue badge past the return date).

## Important: data is not persisted
All data lives **in memory** while the app runs. When you stop or restart
the server, everything resets to the built-in sample items. This is by design
(no database). To keep data between runs, you'd need to add file or DB storage.
