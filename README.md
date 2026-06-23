# University Equipment Lending

A tiny CRUD web app to track items the university lends to professors.
Add, edit, remove items, and assign / return them.

## Tech
- Pure Python **standard library** — no database, no `pip install`.
- Runs on `http.server` at `http://localhost:8000`.
- Server-rendered HTML frontend.

## Run

```bash
python3 app.py
```

Then open **http://localhost:8000** in your browser.
Stop with `Ctrl+C`.

## Login

The app is gated by a login. Two demo accounts (in-memory, reset on restart):

| Username | Password   | Can do                                   |
|----------|------------|------------------------------------------|
| `admin`  | `password` | Everything: add, edit, remove, assign, return, view |
| `staff`  | `staff`    | View items + who's assigned; assign / return only   |

Sessions are stored in memory (cookie-based) and reset when the server restarts.

## Features
- **Add** an item (admin only; confirm prompt).
- **Edit** an item in a **modal popup** (admin only; confirm on save).
- **Remove** an item (admin only; confirm prompt).
- **Assign** an available item to a professor (admin + staff; records the date).
- **Return** an assigned item (admin + staff; marks it available again).
- **View** the items table with description and who each item is assigned to.

## Important: data is not persisted
All data lives **in memory** while the app runs. When you stop or restart
the server, everything resets to the built-in sample items. This is by design
(no database). To keep data between runs, you'd need to add file or DB storage.
