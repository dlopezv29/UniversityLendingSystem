import html
import secrets
from datetime import date
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HOST = "localhost"
PORT = 8000

# ---------------------------------------------------------------------------
# Accounts & sessions (in-memory, reset on restart)
# ---------------------------------------------------------------------------
USERS: dict[str, dict] = {
    "admin": {"password": "password", "role": "admin"},
    "staff": {"password": "staff", "role": "staff"},
}
SESSIONS: dict[str, str] = {}  # token -> username


def new_token() -> str:
    return secrets.token_hex(16)

# ---------------------------------------------------------------------------
# In-memory data store (resets on restart)
# ---------------------------------------------------------------------------
ITEMS: list[dict] = [
    {
        "id": 1,
        "name": "Dell Latitude Laptop",
        "category": "Laptop",
        "description": "14-inch, Windows 11, charger included",
        "status": "available",
        "assigned_to": "",
        "assigned_on": "",
    },
    {
        "id": 2,
        "name": "Epson Projector",
        "category": "Projector",
        "description": "Full HD, HDMI + VGA",
        "status": "assigned",
        "assigned_to": "Prof. García",
        "assigned_on": "2026-06-20",
    },
    {
        "id": 3,
        "name": "Logitech Webcam C920",
        "category": "Peripheral",
        "description": "1080p USB webcam",
        "status": "available",
        "assigned_to": "",
        "assigned_on": "",
    },
]
NEXT_ID = 4


def find_item(item_id: int):
    """Return the item dict with the given id, or None."""
    for item in ITEMS:
        if item["id"] == item_id:
            return item
    return None


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------
def render_layout(title: str, body: str, user: dict | None = None) -> str:
    """Wrap page body in the shared HTML shell with embedded CSS.

    When ``user`` is given, the header shows who is signed in plus a logout
    button (with confirmation).
    """
    if user:
        user_bar = f"""
  <div class="userbar">
    <span>{html.escape(user['name'])}<span class="role">{html.escape(user['role'])}</span></span>
    <form class="inline" action="/logout" method="post" onsubmit="return confirm('Log out?');">
      <button class="btn-ghost btn-sm" type="submit">Log out</button>
    </form>
  </div>"""
    else:
        user_bar = ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {{
    /* Universidad Latina de Costa Rica brand palette */
    --primary:#FFC72C; --primary-dark:#e6b21f; --on-primary:#4D4D4F;
    --accent:#97D700; --accent-dark:#86c200; --on-accent:#4D4D4F;
    --header:#2F4050; --header-soft:#3a4d61;
    --bg:#f3f4f6; --surface:#ffffff; --fg:#4D4D4F; --fg-soft:#5f6163;
    --muted:#8a8c8e; --line:#e4e7eb; --line-soft:#eef1f4;
    --danger:#ED5565; --danger-soft:#fdecee;
    --ok:#7ab800; --ok-soft:#f3fae0; --warn:#b45309; --warn-soft:#fffbeb;
    --radius:8px;
  }}
  * {{ box-sizing:border-box; }}
  body {{ font-family:'Inter',-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
          margin:0; background:var(--bg); color:var(--fg); font-size:14px;
          line-height:1.5; -webkit-font-smoothing:antialiased; }}
  header {{ background:var(--header); color:#fff; padding:16px 24px;
            border-bottom:3px solid var(--primary);
            display:flex; align-items:center; justify-content:space-between; gap:16px; }}
  .brand {{ display:flex; align-items:center; gap:10px; }}
  .brand svg {{ width:22px; height:22px; color:var(--primary); flex:none; }}
  header h1 {{ margin:0; font-size:16px; font-weight:600; letter-spacing:-.01em; }}
  header p {{ margin:1px 0 0; color:rgba(255,255,255,.7); font-size:12px; }}
  .container {{ max-width:980px; margin:28px auto; padding:0 20px; }}
  .card {{ background:var(--surface); border:1px solid var(--line); border-radius:12px;
           padding:20px 22px; margin-bottom:20px; }}
  .card-head {{ display:flex; align-items:center; justify-content:space-between;
                gap:12px; margin-bottom:16px; }}
  h2 {{ font-size:15px; font-weight:600; margin:0; letter-spacing:-.01em; }}
  table {{ width:100%; border-collapse:collapse; }}
  th,td {{ text-align:left; padding:11px 14px; border-bottom:1px solid var(--line-soft);
           font-size:13px; vertical-align:middle; }}
  th {{ font-size:11px; text-transform:uppercase; letter-spacing:.05em;
        font-weight:600; color:var(--muted); }}
  tbody tr:hover {{ background:#fafbfc; }}
  tr:last-child td {{ border-bottom:none; }}
  td strong {{ font-weight:600; }}
  .status {{ display:inline-flex; align-items:center; gap:6px; font-size:12px;
             font-weight:500; }}
  .status .dot {{ width:7px; height:7px; border-radius:50%; flex:none; }}
  .status.available {{ color:var(--ok); }}
  .status.available .dot {{ background:var(--ok); }}
  .status.assigned {{ color:var(--warn); }}
  .status.assigned .dot {{ background:var(--warn); }}
  form.inline {{ display:inline; }}
  input,select,textarea {{ font:inherit; font-size:14px; padding:9px 11px;
           border:1px solid #cbd5e1; border-radius:var(--radius); width:100%;
           background:var(--surface); color:var(--fg);
           transition:border-color .15s ease, box-shadow .15s ease; }}
  input:focus,select:focus,textarea:focus {{ outline:none; border-color:var(--primary);
           box-shadow:0 0 0 3px rgba(255,199,44,.35); }}
  textarea {{ resize:vertical; min-height:60px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr));
           gap:14px; margin-bottom:14px; }}
  label {{ display:block; font-size:12px; font-weight:500; color:var(--fg-soft); margin-bottom:5px; }}
  button {{ font:inherit; font-size:13px; cursor:pointer; border:1px solid transparent;
            border-radius:var(--radius); padding:9px 15px; font-weight:500;
            transition:background .15s ease, border-color .15s ease, color .15s ease; }}
  .btn-primary {{ background:var(--primary); color:var(--on-primary); font-weight:600; }}
  .btn-primary:hover {{ background:var(--primary-dark); }}
  .btn-accent {{ background:var(--accent); color:var(--on-accent); font-weight:600; }}
  .btn-accent:hover {{ background:var(--accent-dark); }}
  .btn-sm {{ padding:6px 11px; font-size:12px; }}
  .btn-ghost {{ background:var(--surface); color:var(--fg-soft); border-color:var(--line); }}
  .btn-ghost:hover {{ background:var(--bg); border-color:#cbd5e1; }}
  .btn-danger {{ background:var(--surface); color:var(--danger); border-color:#fecaca; }}
  .btn-danger:hover {{ background:var(--danger-soft); border-color:var(--danger); }}
  .actions {{ display:flex; gap:6px; flex-wrap:wrap; align-items:center; }}
  .assign-row {{ display:flex; gap:6px; }}
  .assign-row input {{ width:auto; flex:1; padding:6px 9px; font-size:13px; }}
  a {{ color:var(--header); font-weight:500; text-decoration:none; }}
  .muted {{ color:var(--muted); font-size:13px; }}
  .userbar {{ display:flex; align-items:center; gap:12px; }}
  .userbar span {{ font-size:13px; color:rgba(255,255,255,.92); }}
  .userbar .role {{ display:inline-block; padding:1px 8px; border-radius:999px;
            background:rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.2);
            font-size:11px; font-weight:500; color:#fff; margin-left:4px; }}
  .userbar .btn-ghost {{ background:rgba(255,255,255,.1); color:#fff;
            border-color:rgba(255,255,255,.25); }}
  .userbar .btn-ghost:hover {{ background:rgba(255,255,255,.2); border-color:rgba(255,255,255,.4); }}
  .login-wrap {{ min-height:calc(100vh - 120px); display:flex; align-items:center;
            justify-content:center; }}
  .login-card {{ width:100%; max-width:360px; margin:0; border-top:4px solid var(--primary); }}
  .login-card h2 {{ margin-bottom:4px; }}
  .login-card .sub {{ color:var(--muted); font-size:13px; margin:0 0 18px; }}
  .login-card .field {{ margin-bottom:14px; }}
  .error {{ background:var(--danger-soft); color:var(--danger);
            border:1px solid #fecaca; padding:9px 12px;
            border-radius:var(--radius); font-size:13px; margin-bottom:14px; }}
  .collapse {{ display:none; }}
  .collapse.open {{ display:block; }}
  /* Edit modal */
  .modal {{ display:none; position:fixed; inset:0; background:rgba(15,23,42,.45);
            z-index:50; align-items:flex-start; justify-content:center; padding:48px 16px; }}
  .modal.open {{ display:flex; }}
  .modal .card {{ width:100%; max-width:520px; margin:0;
            box-shadow:0 10px 40px rgba(15,23,42,.18); animation:pop .15s ease; }}
  @keyframes pop {{ from {{ opacity:0; transform:translateY(-6px); }}
                    to {{ opacity:1; transform:none; }} }}
  @media (prefers-reduced-motion: reduce) {{
    * {{ animation:none !important; transition:none !important; }}
  }}
</style>
</head>
<body>
<header>
  <div class="brand">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
         stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M22 10v6M2 10l10-5 10 5-10 5z"></path>
      <path d="M6 12v5c3 3 9 3 12 0v-5"></path>
    </svg>
    <div>
      <h1>Universidad Latina de Costa Rica</h1>
      <p>Sistema de prestamo a profesores</p>
    </div>
  </div>{user_bar}
</header>
<div class="container">
{body}
</div>
</body>
</html>"""


def render_index(user: dict) -> str:
    """List page: items table + (admin-only) add form + edit modal."""
    is_admin = user["role"] == "admin"
    if ITEMS:
        rows = "".join(render_row(item, user) for item in ITEMS)
    else:
        rows = '<tr><td colspan="5" class="muted">No items yet.</td></tr>'

    add_button = (
        '<button class="btn-accent btn-sm" type="button" onclick="toggleAdd(this)" '
        'id="addToggle">+ New item</button>'
        if is_admin
        else ""
    )

    add_form = ""
    modal = ""
    if is_admin:
        add_form = """
  <div class="collapse" id="addForm">
    <form action="/add" method="post" onsubmit="return confirm('Add this item?');"
          style="border-top:1px solid var(--line-soft); margin-top:16px; padding-top:18px;">
      <div class="grid">
        <div><label>Name *</label><input name="name" required placeholder="e.g. MacBook Air"></div>
        <div><label>Category</label><input name="category" placeholder="e.g. Laptop"></div>
      </div>
      <div style="margin-bottom:14px">
        <label>Description</label>
        <textarea name="description" placeholder="Notes, accessories, condition..."></textarea>
      </div>
      <div class="actions">
        <button class="btn-primary" type="submit">Add item</button>
        <button class="btn-ghost" type="button" onclick="toggleAdd(document.getElementById('addToggle'))">Cancel</button>
      </div>
    </form>
  </div>
"""
        modal = """
<div class="modal" id="editModal" onclick="if(event.target===this)closeEdit()">
  <div class="card">
    <h2>Edit item</h2>
    <form action="/edit" method="post" onsubmit="return confirm('Save changes?');">
      <input type="hidden" name="id" id="edit-id">
      <div class="grid">
        <div><label>Name *</label><input name="name" id="edit-name" required></div>
        <div><label>Category</label><input name="category" id="edit-category"></div>
      </div>
      <div style="margin-bottom:16px">
        <label>Description</label>
        <textarea name="description" id="edit-description"></textarea>
      </div>
      <div class="actions">
        <button class="btn-primary" type="submit">Save changes</button>
        <button class="btn-ghost" type="button" onclick="closeEdit()">Cancel</button>
      </div>
    </form>
  </div>
</div>
<script>
  function openEdit(btn) {
    var m = document.getElementById('editModal');
    document.getElementById('edit-id').value = btn.dataset.id;
    document.getElementById('edit-name').value = btn.dataset.name;
    document.getElementById('edit-category').value = btn.dataset.category;
    document.getElementById('edit-description').value = btn.dataset.description;
    m.classList.add('open');
  }
  function closeEdit() {
    document.getElementById('editModal').classList.remove('open');
  }
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeEdit();
  });
  function toggleAdd(btn) {
    var f = document.getElementById('addForm');
    var open = f.classList.toggle('open');
    btn.textContent = open ? 'Close' : '+ New item';
    if (open) f.querySelector('input[name=name]').focus();
  }
</script>
"""

    table = f"""
<div class="card">
  <div class="card-head">
    <h2>Items <span class="muted" style="font-weight:400">({len(ITEMS)})</span></h2>
    {add_button}
  </div>
  <table>
    <thead>
      <tr><th>Item</th><th>Category</th><th>Status</th><th>Assigned to</th><th style="text-align:right">Actions</th></tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>{add_form}
</div>
"""
    return render_layout("Equipment Lending", table + modal, user)


def render_row(item: dict, user: dict) -> str:
    """One table row for an item."""
    is_admin = user["role"] == "admin"
    status = item["status"]
    badge = f'<span class="status {status}"><span class="dot"></span>{html.escape(status)}</span>'

    if status == "assigned":
        assigned = (
            f'{html.escape(item["assigned_to"])}'
            f'<div class="muted">since {html.escape(item["assigned_on"])}</div>'
        )
        assign_control = f"""
        <form class="inline" action="/return" method="post">
          <input type="hidden" name="id" value="{item['id']}">
          <button class="btn-ghost btn-sm" type="submit">Return</button>
        </form>"""
    else:
        assigned = '<span class="muted">—</span>'
        assign_control = f"""
        <form class="inline" action="/assign" method="post">
          <input type="hidden" name="id" value="{item['id']}">
          <div class="assign-row">
            <input name="assigned_to" required placeholder="Professor name">
            <button class="btn-primary btn-sm" type="submit">Assign</button>
          </div>
        </form>"""

    desc = (
        f'<div class="muted">{html.escape(item["description"])}</div>'
        if item["description"]
        else ""
    )

    if is_admin:
        admin_actions = f"""
      <button class="btn-ghost btn-sm" type="button"
              data-id="{item['id']}"
              data-name="{html.escape(item['name'], quote=True)}"
              data-category="{html.escape(item['category'], quote=True)}"
              data-description="{html.escape(item['description'], quote=True)}"
              onclick="openEdit(this)">Edit</button>
      <form class="inline" action="/remove" method="post"
            onsubmit="return confirm('Remove this item?');">
        <input type="hidden" name="id" value="{item['id']}">
        <button class="btn-danger btn-sm" type="submit">Remove</button>
      </form>"""
    else:
        admin_actions = ""

    return f"""
<tr>
  <td><strong>{html.escape(item['name'])}</strong>{desc}</td>
  <td>{html.escape(item['category']) or '<span class="muted">—</span>'}</td>
  <td>{badge}</td>
  <td>{assigned}</td>
  <td>
    <div class="actions" style="justify-content:flex-end">
      {assign_control}
      {admin_actions}
    </div>
  </td>
</tr>"""


def render_login(error: bool = False) -> str:
    """Login page with username + password."""
    err = '<div class="error">Invalid credentials. Try again.</div>' if error else ""
    body = f"""
<div class="login-wrap">
  <div class="card login-card">
    <h2>Sign in</h2>
    {err}
    <form action="/login" method="post">
      <div class="field"><label>Username</label>
        <input name="username" required autofocus autocomplete="username" placeholder="admin or staff"></div>
      <div class="field"><label>Password</label>
        <input name="password" type="password" required autocomplete="current-password"></div>
      <button class="btn-primary" type="submit" style="width:100%">Sign in</button>
    </form>
  </div>
</div>
"""
    return render_layout("Sign in", body)


def render_404() -> str:
    body = (
        '<div class="card"><h2>404 — Not found</h2>'
        '<p class="muted" style="margin:6px 0 16px">That page does not exist.</p>'
        '<a class="btn-primary" href="/" '
        'style="display:inline-block;color:#fff;padding:9px 15px;border-radius:8px">Back to items</a></div>'
    )
    return render_layout("Not found", body)


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    # --- helpers --------------------------------------------------------
    def _send_html(self, code: int, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, location: str = "/", cookie: str | None = None) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()

    def _read_form(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        parsed = parse_qs(raw, keep_blank_values=True)
        return {k: v[0] for k, v in parsed.items()}

    def current_user(self) -> dict | None:
        """Return {'name', 'role'} for the signed-in user, or None."""
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        cookie = SimpleCookie()
        cookie.load(raw)
        morsel = cookie.get("session")
        if not morsel:
            return None
        username = SESSIONS.get(morsel.value)
        if username and username in USERS:
            return {"name": username, "role": USERS[username]["role"]}
        return None

    def log_message(self, fmt, *args):  # quieter console
        return

    # --- routes ---------------------------------------------------------
    def do_GET(self):
        url = urlparse(self.path)
        user = self.current_user()

        if url.path == "/login":
            if user:
                self._redirect("/")
            else:
                error = parse_qs(url.query).get("error", ["0"])[0] == "1"
                self._send_html(200, render_login(error))
            return

        if not user:
            self._redirect("/login")
            return

        if url.path == "/":
            self._send_html(200, render_index(user))
        else:
            self._send_html(404, render_404())

    def do_POST(self):
        global NEXT_ID
        url = urlparse(self.path)
        form = self._read_form()
        user = self.current_user()

        if url.path == "/login":
            username = form.get("username", "").strip()
            password = form.get("password", "")
            account = USERS.get(username)
            if account and account["password"] == password:
                token = new_token()
                SESSIONS[token] = username
                self._redirect("/", cookie=f"session={token}; HttpOnly; Path=/; SameSite=Lax")
            else:
                self._redirect("/login?error=1")
            return

        if url.path == "/logout":
            raw = self.headers.get("Cookie")
            if raw:
                cookie = SimpleCookie()
                cookie.load(raw)
                morsel = cookie.get("session")
                if morsel:
                    SESSIONS.pop(morsel.value, None)
            self._redirect("/login", cookie="session=; HttpOnly; Path=/; Max-Age=0")
            return

        # All remaining routes require authentication.
        if not user:
            self._redirect("/login")
            return

        # Admin-only mutations.
        if url.path in ("/add", "/edit", "/remove") and user["role"] != "admin":
            self._redirect("/")
            return

        if url.path == "/add":
            name = form.get("name", "").strip()
            if name:
                ITEMS.append({
                    "id": NEXT_ID,
                    "name": name,
                    "category": form.get("category", "").strip(),
                    "description": form.get("description", "").strip(),
                    "status": "available",
                    "assigned_to": "",
                    "assigned_on": "",
                })
                NEXT_ID += 1
            self._redirect("/")

        elif url.path == "/edit":
            item = find_item(int(form.get("id", 0) or 0))
            if item:
                name = form.get("name", "").strip()
                if name:
                    item["name"] = name
                item["category"] = form.get("category", "").strip()
                item["description"] = form.get("description", "").strip()
            self._redirect("/")

        elif url.path == "/remove":
            item = find_item(int(form.get("id", 0) or 0))
            if item:
                ITEMS.remove(item)
            self._redirect("/")

        elif url.path == "/assign":
            item = find_item(int(form.get("id", 0) or 0))
            prof = form.get("assigned_to", "").strip()
            if item and prof:
                item["status"] = "assigned"
                item["assigned_to"] = prof
                item["assigned_on"] = date.today().isoformat()
            self._redirect("/")

        elif url.path == "/return":
            item = find_item(int(form.get("id", 0) or 0))
            if item:
                item["status"] = "available"
                item["assigned_to"] = ""
                item["assigned_on"] = ""
            self._redirect("/")

        else:
            self._send_html(404, render_404())


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"University Equipment Lending running at http://{HOST}:{PORT}")
    print("Data is in-memory only — it resets when you stop the server.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
