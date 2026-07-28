"""HTML rendering — the full server-rendered frontend.

Every function returns an HTML string. State is read live from the ``data``
module, which queries the database and hands back plain dicts. This module only
reads — it never writes.
"""

from __future__ import annotations

import hashlib
import html
import json
from datetime import date

import data


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------
def render_layout(
    title: str, body: str, user: dict | None = None, active_nav: str = ""
) -> str:
    """Wrap page body in the shared HTML shell with embedded CSS.

    When ``user`` is given, the header shows who is signed in plus a logout
    button (with confirmation). ``active_nav`` ("items" | "professors") drives
    the admin section tabs.
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

    nav = ""
    if user and user["role"] == "admin":
        items_cls = "active" if active_nav == "items" else ""
        profs_cls = "active profs" if active_nav == "professors" else ""
        metrics_cls = "active" if active_nav == "metrics" else ""
        nav = f"""
  <nav class="mainnav" aria-label="Sections">
    <a class="{items_cls}" href="/"{' aria-current="page"' if active_nav == 'items' else ''}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
           stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <rect x="3" y="3" width="7" height="7" rx="1"></rect>
        <rect x="14" y="3" width="7" height="7" rx="1"></rect>
        <rect x="3" y="14" width="7" height="7" rx="1"></rect>
        <rect x="14" y="14" width="7" height="7" rx="1"></rect>
      </svg>Item Management</a>
    <a class="{profs_cls}" href="/professors"{' aria-current="page"' if active_nav == 'professors' else ''}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
           stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
        <circle cx="9" cy="7" r="4"></circle>
        <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"></path>
      </svg>Professors Management</a>
    <a class="{metrics_cls}" href="/metrics"{' aria-current="page"' if active_nav == 'metrics' else ''}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
           stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M3 3v18h18"></path>
        <path d="M7 15l4-5 3 3 5-7"></path>
      </svg>Performance</a>
  </nav>"""
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
    --accent:#97D700; --accent-dark:#86c200; --on-accent:#4D4D4F; --accent-soft:#eef8d6;
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
  .status.disabled {{ color:var(--muted); }}
  .status.disabled .dot {{ background:var(--muted); }}
  .badge-overdue {{ display:inline-block; margin-left:6px; padding:1px 7px;
             border-radius:999px; background:var(--danger-soft); color:var(--danger);
             font-size:11px; font-weight:600; }}
  .toolbar {{ display:flex; gap:8px; flex-wrap:wrap; }}
  .filters {{ display:flex; gap:14px; flex-wrap:wrap; margin:0 0 16px; }}
  .filters > div {{ min-width:170px; }}
  .filters select {{ width:auto; min-width:170px; }}
  .filter-check {{ display:flex; align-items:flex-end; min-width:0; }}
  .filter-check label {{ display:flex; align-items:center; gap:7px; font-size:13px;
            font-weight:500; cursor:pointer; padding-bottom:9px; white-space:nowrap; }}
  .filter-check input {{ width:auto; margin:0; }}
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
            border-radius:var(--radius); padding:9px 15px; font-weight:500; white-space:nowrap;
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
  /* Header section tabs */
  .mainnav {{ display:flex; gap:6px; }}
  .mainnav a {{ display:inline-flex; align-items:center; gap:8px; padding:8px 14px;
            border-radius:8px; font-size:13px; font-weight:500; white-space:nowrap;
            color:rgba(255,255,255,.75); border:1px solid transparent; }}
  .mainnav a svg {{ width:16px; height:16px; flex:none; }}
  .mainnav a:hover {{ background:rgba(255,255,255,.1); color:#fff; }}
  .mainnav a.active {{ background:var(--primary); color:var(--on-primary); font-weight:600; }}
  .mainnav a.active.profs {{ background:var(--accent); color:var(--on-accent); }}
  /* Professors page (distinct card-grid view) */
  .page-head {{ display:flex; align-items:flex-end; justify-content:space-between;
            gap:16px; margin-bottom:20px; flex-wrap:wrap; }}
  .page-head h2 {{ font-size:20px; }}
  .page-head .lead {{ margin:4px 0 0; color:var(--muted); font-size:13px; }}
  .page-head .accent-rule {{ height:3px; width:44px; background:var(--accent);
            border-radius:999px; margin-bottom:12px; }}
  .prof-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(250px,1fr));
            gap:16px; margin-bottom:20px; }}
  .prof-card {{ background:var(--surface); border:1px solid var(--line); border-radius:12px;
            border-top:3px solid var(--accent); padding:18px;
            display:flex; flex-direction:column; gap:14px; }}
  .prof-card .top {{ display:flex; align-items:center; gap:12px; }}
  .avatar {{ width:44px; height:44px; border-radius:50%; background:var(--accent-soft);
            color:var(--accent-dark); display:flex; align-items:center; justify-content:center;
            font-weight:700; font-size:15px; flex:none; letter-spacing:.02em; }}
  .prof-card .name {{ font-weight:600; font-size:15px; line-height:1.2; }}
  .prof-card .dept {{ font-size:12px; color:var(--muted); margin-top:2px; }}
  .prof-metric {{ display:flex; align-items:baseline; gap:7px; padding:11px 14px;
            background:var(--bg); border-radius:8px; }}
  .prof-metric b {{ font-size:22px; font-weight:700; font-variant-numeric:tabular-nums;
            color:var(--fg); }}
  .prof-metric span {{ font-size:12px; color:var(--muted); }}
  .prof-metric-btn {{ width:100%; border:1px solid var(--line); cursor:pointer;
            text-align:left; transition:border-color .12s, background .12s; }}
  .prof-metric-btn:hover {{ border-color:var(--accent); background:var(--accent-soft); }}
  .prof-items {{ margin-top:-6px; overflow-x:auto; }}
  .prof-items table {{ font-size:12px; }}
  .prof-card .actions {{ margin-top:auto; }}
  .empty {{ text-align:center; padding:44px 20px; color:var(--muted); }}
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
  /* Return receipt */
  .receipt {{ text-align:center; max-width:420px; margin:0 auto; }}
  .qr-box {{ display:inline-block; padding:14px; background:#fff;
            border:1px solid var(--line); border-radius:12px; margin:4px 0 18px; }}
  .qr-box svg {{ display:block; width:180px; height:180px; }}
  .return-code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
            font-size:26px; font-weight:700; letter-spacing:.06em; color:var(--fg);
            background:var(--bg); border:1px dashed var(--line); border-radius:10px;
            padding:12px 16px; margin:0 0 10px; }}
  .receipt .actions {{ justify-content:center; }}
  /* Performance page */
  .kpis {{ display:grid; gap:12px; margin-bottom:20px;
           grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); }}
  .kpi {{ background:var(--surface); border:1px solid var(--line);
          border-radius:12px; padding:14px 16px; }}
  .kpi b {{ display:block; font-size:22px; font-weight:700;
            font-variant-numeric:tabular-nums; letter-spacing:-.02em; }}
  .kpi span {{ display:block; font-size:11px; text-transform:uppercase;
               letter-spacing:.05em; color:var(--muted); margin-top:2px; }}
  .kpi small {{ display:block; color:var(--muted); font-size:12px; margin-top:6px; }}
  .num {{ text-align:right; font-variant-numeric:tabular-nums;
          font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px; }}
  th.num {{ font-family:inherit; }}
  .metric-name {{ font-weight:500; }}
  .metric-name code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
                       font-size:12px; }}
  .row-lock td {{ background:var(--warn-soft); }}
  .table-scroll {{ overflow-x:auto; }}
  .hint {{ color:var(--muted); font-size:12px; margin:0 0 14px; }}
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
  </div>{nav}{user_bar}
</header>
<div class="container">
{body}
</div>
</body>
</html>"""


def render_index(
    user: dict,
    category_filter: str = "",
    overdue_only: bool = False,
    request_error: str | None = None,
    request_values: dict | None = None,
    add_error: str | None = None,
    add_values: dict | None = None,
    return_error: str | None = None,
    return_error_id: str | None = None,
) -> str:
    """Item Management page: items table + filters + (admin-only) add form and
    New Request modal. Professors now live on their own page."""
    is_admin = user["role"] == "admin"
    professor_name = user.get("professor", "")

    # Fetched once and reused below, rather than re-querying per section.
    items = data.all_items()

    visible_items = items
    if category_filter:
        visible_items = [i for i in visible_items if i["category"] == category_filter]
    if overdue_only:
        visible_items = [i for i in visible_items if data.is_overdue(i)]

    if visible_items:
        rows = "".join(render_row(item, user) for item in visible_items)
    else:
        rows = '<tr><td colspan="5" class="muted">No items match.</td></tr>'

    cat_option_tags = "".join(
        f'<option value="{html.escape(c)}">{html.escape(c)}</option>' for c in data.CATEGORIES
    )
    filter_cat_options = "".join(
        f'<option value="{html.escape(c)}"{" selected" if c == category_filter else ""}>'
        f'{html.escape(c)}</option>'
        for c in data.CATEGORIES
    )
    assigned_to_me_filter = "" if is_admin else f"""
  <div class="filter-check">
    <label><input type="checkbox" id="assignedToMe" onchange="applyRowFilters()"
      {' checked' if professor_name else ''}> Assigned to me</label>
  </div>
"""
    filters = f"""
<form class="filters" method="get" action="/">
  <div>
    <label>Category</label>
    <select name="category" onchange="this.form.submit()">
      <option value=""{' selected' if not category_filter else ''}>All categories</option>
      {filter_cat_options}
    </select>
  </div>
  <div>
    <label>Overdue</label>
    <select name="overdue" onchange="this.form.submit()">
      <option value=""{' selected' if not overdue_only else ''}>All items</option>
      <option value="1"{' selected' if overdue_only else ''}>Overdue only</option>
    </select>
  </div>
  <div>
    <label>Item Name</label>
    <input type="search" id="nameFilter" placeholder="Type to filter…"
           oninput="applyRowFilters()"
           onkeydown="if(event.key==='Enter')event.preventDefault()">
  </div>
  {assigned_to_me_filter}
</form>
"""

    toolbar = ""
    add_form = ""
    edit_modal = ""
    request_modal = ""
    return_modal = ""
    if is_admin:
        toolbar = """
    <div class="toolbar">
      <button class="btn-accent btn-sm" type="button" onclick="openAdd()">+ New item</button>
      <button class="btn-primary btn-sm" type="button" onclick="openRequest()">+ New request</button>
    </div>
"""
        av = add_values or {}
        add_id_val = html.escape(av.get("id", ""), quote=True)
        add_name_val = html.escape(av.get("name", ""), quote=True)
        add_category_val = av.get("category", "")
        add_description_val = html.escape(av.get("description", ""))
        add_cat_options = "".join(
            f'<option value="{html.escape(c)}"{" selected" if c == add_category_val else ""}>'
            f'{html.escape(c)}</option>'
            for c in data.CATEGORIES
        )
        add_err_html = f'<div class="error">{html.escape(add_error)}</div>' if add_error else ""
        add_open_cls = " open" if add_error else ""
        add_form = f"""
<div class="modal{add_open_cls}" id="addModal" onclick="if(event.target===this)closeAdd()">
  <div class="card">
    <h2>New item</h2>
    {add_err_html}
    <form action="/add" method="post" onsubmit="return confirm('Add this item?');">
      <div class="grid">
        <div><label>ID *</label><input name="id" required placeholder="e.g. EQ-001" value="{add_id_val}"></div>
        <div><label>Name *</label><input name="name" required placeholder="e.g. MacBook Air" value="{add_name_val}"></div>
        <div><label>Category *</label>
          <select name="category" required>
            <option value="" disabled{"" if add_category_val else " selected"}>Select category</option>
            {add_cat_options}
          </select>
        </div>
      </div>
      <div style="margin-bottom:16px">
        <label>Description</label>
        <textarea name="description" placeholder="Notes, accessories, condition...">{add_description_val}</textarea>
      </div>
      <div class="actions">
        <button class="btn-primary" type="submit">Add item</button>
        <button class="btn-ghost" type="button" onclick="closeAdd()">Cancel</button>
      </div>
    </form>
  </div>
</div>
"""
        edit_modal = f"""
<div class="modal" id="editModal" onclick="if(event.target===this)closeEdit()">
  <div class="card">
    <h2>Edit item</h2>
    <form action="/edit" method="post" onsubmit="return confirm('Save changes?');">
      <input type="hidden" name="id" id="edit-id">
      <div class="grid">
        <div><label>Name *</label><input name="name" id="edit-name" required></div>
        <div><label>Category *</label>
          <select name="category" id="edit-category" required>
            {cat_option_tags}
          </select>
        </div>
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
"""
        available_items = [i for i in items if i["status"] == "available"]
        item_options = "".join(
            f'<option value="{html.escape(i["name"], quote=True)}">' for i in available_items
        )
        professor_options = "".join(
            f'<option value="{html.escape(p["name"], quote=True)}">'
            for p in data.all_professors()
        )
        today_iso = date.today().isoformat()
        rv = request_values or {}
        item_name_val = html.escape(rv.get("item_name", ""), quote=True)
        professor_name_val = html.escape(rv.get("professor_name", ""), quote=True)
        due_date_val = rv.get("due_date") or today_iso
        req_err_html = f'<div class="error">{html.escape(request_error)}</div>' if request_error else ""
        req_open_cls = " open" if request_error else ""
        request_modal = f"""
<div class="modal{req_open_cls}" id="requestModal" onclick="if(event.target===this)closeRequest()">
  <div class="card">
    <h2>New request</h2>
    {req_err_html}
    <form action="/request" method="post" onsubmit="return confirm('Create this request?');">
      <div class="grid">
        <div>
          <label>Item *</label>
          <input name="item_name" list="item-options" required
                 placeholder="Start typing an item..." value="{item_name_val}">
          <datalist id="item-options">{item_options}</datalist>
        </div>
        <div>
          <label>Assign to *</label>
          <input name="professor_name" list="professor-options" required
                 placeholder="Start typing a professor..." value="{professor_name_val}">
          <datalist id="professor-options">{professor_options}</datalist>
        </div>
      </div>
      <div style="margin-bottom:16px">
        <label>Return date *</label>
        <input type="date" name="due_date" required min="{today_iso}" value="{due_date_val}">
      </div>
      <div class="actions">
        <button class="btn-primary" type="submit">Create request</button>
        <button class="btn-ghost" type="button" onclick="closeRequest()">Cancel</button>
      </div>
    </form>
  </div>
</div>
"""
    else:
        return_err_html = f'<div class="error">{html.escape(return_error)}</div>' if return_error else ""
        return_open_cls = " open" if return_error else ""
        return_id_val = html.escape(return_error_id or "", quote=True)
        return_modal = f"""
<div class="modal{return_open_cls}" id="returnModal" onclick="if(event.target===this)closeReturn()">
  <div class="card">
    <h2>Return item</h2>
    {return_err_html}
    <form action="/return" method="post">
      <input type="hidden" name="id" id="return-id" value="{return_id_val}">
      <div style="margin-bottom:16px">
        <label>Return code *</label>
        <input name="code" required autofocus placeholder="Enter the code given by the admin">
      </div>
      <div class="actions">
        <button class="btn-primary" type="submit">Confirm return</button>
        <button class="btn-ghost" type="button" onclick="closeReturn()">Cancel</button>
      </div>
    </form>
  </div>
</div>
"""

    table = f"""
<div class="card">
  <div class="card-head">
    <h2>Items <span class="muted" style="font-weight:400">({len(visible_items)})</span></h2>
    {toolbar}
  </div>
  {filters}
  <table>
    <thead>
      <tr><th>Item</th><th>Category</th><th>Status</th><th>Assigned to</th><th style="text-align:right">Actions</th></tr>
    </thead>
    <tbody>{rows}
      <tr id="noMatch" style="display:none"><td colspan="5" class="muted">No items match.</td></tr>
    </tbody>
  </table>
</div>
"""
    filter_script = f"""
<script>
  var MY_NAME = {json.dumps(professor_name)};
  function applyRowFilters() {{
    var q = (document.getElementById('nameFilter').value || '').toLowerCase();
    var assignedCb = document.getElementById('assignedToMe');
    var mine = assignedCb ? assignedCb.checked : false;
    var rows = document.querySelectorAll('table tbody tr[data-name]');
    var shown = 0;
    rows.forEach(function (tr) {{
      var okName = tr.dataset.name.indexOf(q) !== -1;
      var okMine = !mine || tr.dataset.assigned === MY_NAME;
      var show = okName && okMine;
      tr.style.display = show ? '' : 'none';
      if (show) shown++;
    }});
    var nm = document.getElementById('noMatch');
    if (nm) nm.style.display = shown === 0 ? '' : 'none';
  }}
  document.addEventListener('DOMContentLoaded', applyRowFilters);
</script>
"""
    scripts = """
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
  function openRequest() {
    document.getElementById('requestModal').classList.add('open');
  }
  function closeRequest() {
    document.getElementById('requestModal').classList.remove('open');
  }
  function openAdd() {
    var m = document.getElementById('addModal');
    m.classList.add('open');
    m.querySelector('input[name=name]').focus();
  }
  function closeAdd() {
    document.getElementById('addModal').classList.remove('open');
  }
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { closeEdit(); closeRequest(); closeAdd(); }
  });
</script>
"""
    return_scripts = "" if is_admin else """
<script>
  function openReturn(btn) {
    document.getElementById('return-id').value = btn.dataset.id;
    document.getElementById('returnModal').classList.add('open');
  }
  function closeReturn() {
    document.getElementById('returnModal').classList.remove('open');
  }
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { closeReturn(); }
  });
</script>
"""
    body = (
        table + add_form + edit_modal + request_modal + return_modal
        + filter_script + (scripts if is_admin else return_scripts)
    )
    return render_layout("Item Management", body, user, active_nav="items")


def _initials(name: str) -> str:
    """Two-letter avatar initials, ignoring an honorific like 'Prof.'."""
    words = [w for w in name.replace(".", " ").split() if w.lower() not in ("prof", "dr", "mr", "ms", "mrs")]
    words = words or name.split()
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[-1][0]).upper()


def render_professors_page(
    user: dict,
    professors_error: str | None = None,
    add_error: str | None = None,
    add_values: dict | None = None,
) -> str:
    """Professors Management page — a card-grid view, visually distinct from the
    items table. Admin-only; each card shows the professor plus their active
    item count, with edit/remove controls."""
    # Fetched once and reused below, rather than re-querying per card.
    professors = data.all_professors()
    items = data.all_items()

    total = len(professors)
    assigned_total = sum(1 for i in items if i["status"] == "assigned")

    av = add_values or {}
    add_idcard_val = html.escape(av.get("id_card", ""), quote=True)
    add_name_val = html.escape(av.get("name", ""), quote=True)
    add_dept_val = html.escape(av.get("department", ""), quote=True)
    add_err_html = f'<div class="error">{html.escape(add_error)}</div>' if add_error else ""
    add_open_cls = " open" if add_error else ""

    cards = ""
    for p in professors:
        active = [
            i for i in items if i["assigned_to"] == p["name"] and i["status"] == "assigned"
        ]
        count = len(active)
        dept = html.escape(p["department"]) if p["department"] else '<span class="muted">No department</span>'

        if count > 0:
            rows = "".join(
                f"""
        <tr>
          <td>{html.escape(i['name'])}</td>
          <td>{html.escape(i['assigned_on']) or '—'}</td>
          <td>{html.escape(i['due_date']) or '—'}{' <span class="badge-overdue">Overdue</span>' if data.is_overdue(i) else ''}</td>
          <td>
            <form class="inline" action="/return" method="post">
              <input type="hidden" name="id" value="{html.escape(str(i['id']), quote=True)}">
              <button class="btn-ghost btn-sm" type="submit">Return</button>
            </form>
          </td>
        </tr>"""
                for i in active
            )
            metric = f"""
      <button type="button" class="prof-metric prof-metric-btn"
              onclick="toggleProfItems({p['id']})">
        <b>{count}</b><span>active item{'' if count == 1 else 's'}</span>
      </button>
      <div class="collapse prof-items" id="profItems{p['id']}">
        <table>
          <thead><tr><th>Item</th><th>Since</th><th>Due</th><th></th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>"""
        else:
            metric = """
      <div class="prof-metric"><b>0</b><span>active items</span></div>"""

        cards += f"""
    <div class="prof-card">
      <div class="top">
        <div class="avatar" aria-hidden="true">{html.escape(_initials(p['name']))}</div>
        <div>
          <div class="name">{html.escape(p['name'])}</div>
          <div class="idcard muted">ID Card: {html.escape(p['id_card'])}</div>
          <div class="dept">{dept}</div>
        </div>
      </div>{metric}
      <div class="actions">
        <button class="btn-ghost btn-sm" type="button"
                data-id="{p['id']}" data-idcard="{html.escape(p['id_card'], quote=True)}"
                data-name="{html.escape(p['name'], quote=True)}"
                data-department="{html.escape(p['department'], quote=True)}"
                onclick="openProfEdit(this)">Edit</button>
        <form class="inline" action="/professors/remove" method="post"
              onsubmit="return confirm('Remove this professor?');">
          <input type="hidden" name="id" value="{p['id']}">
          <button class="btn-danger btn-sm" type="submit">Remove</button>
        </form>
      </div>
    </div>"""

    grid = f'<div class="prof-grid">{cards}</div>' if professors else (
        '<div class="card empty">No professors yet. Add the first one below.</div>'
    )

    err_html = f'<div class="error">{html.escape(professors_error)}</div>' if professors_error else ""

    body = f"""
{err_html}
<div class="page-head">
  <div>
    <div class="accent-rule"></div>
    <h2>Professors</h2>
    <p class="lead">{total} professor{'' if total == 1 else 's'} · {assigned_total} item{'' if assigned_total == 1 else 's'} currently on loan</p>
  </div>
  <button class="btn-accent" type="button" onclick="toggleAddProf(this)" id="addProfToggle">+ Add professor</button>
</div>

<div class="card collapse{add_open_cls}" id="addProfForm">
  <h2 style="margin-bottom:16px">New professor</h2>
  {add_err_html}
  <form action="/professors/add" method="post">
    <div class="grid">
      <div><label>ID Card *</label><input name="id_card" required placeholder="e.g. PROF-004" value="{add_idcard_val}"></div>
      <div><label>Name *</label><input name="name" required placeholder="e.g. Prof. Smith" value="{add_name_val}"></div>
      <div><label>Department</label><input name="department" placeholder="e.g. Engineering" value="{add_dept_val}"></div>
    </div>
    <div class="actions">
      <button class="btn-primary" type="submit">Add professor</button>
      <button class="btn-ghost" type="button" onclick="toggleAddProf(document.getElementById('addProfToggle'))">Cancel</button>
    </div>
  </form>
</div>

{grid}

<div class="modal" id="profEditModal" onclick="if(event.target===this)closeProfEdit()">
  <div class="card">
    <h2>Edit professor</h2>
    <form action="/professors/edit" method="post" onsubmit="return confirm('Save changes?');">
      <input type="hidden" name="id" id="profedit-id">
      <div class="grid">
        <div><label>ID Card *</label><input name="id_card" id="profedit-idcard" required></div>
        <div><label>Name *</label><input name="name" id="profedit-name" required></div>
        <div><label>Department</label><input name="department" id="profedit-department"></div>
      </div>
      <div class="actions">
        <button class="btn-primary" type="submit">Save changes</button>
        <button class="btn-ghost" type="button" onclick="closeProfEdit()">Cancel</button>
      </div>
    </form>
  </div>
</div>

<script>
  function toggleAddProf(btn) {{
    var f = document.getElementById('addProfForm');
    var open = f.classList.toggle('open');
    btn.textContent = open ? 'Close' : '+ Add professor';
    if (open) f.querySelector('input[name=name]').focus();
  }}
  function openProfEdit(btn) {{
    document.getElementById('profedit-id').value = btn.dataset.id;
    document.getElementById('profedit-idcard').value = btn.dataset.idcard;
    document.getElementById('profedit-name').value = btn.dataset.name;
    document.getElementById('profedit-department').value = btn.dataset.department;
    document.getElementById('profEditModal').classList.add('open');
  }}
  function toggleProfItems(id) {{
    document.getElementById('profItems' + id).classList.toggle('open');
  }}
  function closeProfEdit() {{
    document.getElementById('profEditModal').classList.remove('open');
  }}
  document.addEventListener('keydown', function (e) {{
    if (e.key === 'Escape') {{ closeProfEdit(); }}
  }});
</script>
"""
    return render_layout("Professors Management", body, user, active_nav="professors")


def _ms(value: float) -> str:
    """Milliseconds with a sensible number of digits for the magnitude."""
    if value >= 100:
        return f"{value:.0f}"
    if value >= 1:
        return f"{value:.2f}"
    return f"{value:.3f}"


def _metric_table(rows: list, label: str) -> str:
    """One sortable-looking stats table; `rows` come from metrics.snapshot()."""
    if not rows:
        return f'<p class="muted">No {label} recorded yet.</p>'

    body_rows = ""
    for row in rows:
        highlight = ' class="row-lock"' if row["name"] == "_lock wait" else ""
        body_rows += f"""
        <tr{highlight}>
          <td class="metric-name"><code>{html.escape(row['name'])}</code></td>
          <td class="num">{row['count']}</td>
          <td class="num">{_ms(row['mean_ms'])}</td>
          <td class="num">{_ms(row['p50_ms'])}</td>
          <td class="num">{_ms(row['p95_ms'])}</td>
          <td class="num">{_ms(row['p99_ms'])}</td>
          <td class="num">{_ms(row['max_ms'])}</td>
          <td class="num">{_ms(row['total_ms'])}</td>
        </tr>"""

    return f"""
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>{html.escape(label)}</th>
            <th class="num">Calls</th>
            <th class="num">Mean ms</th>
            <th class="num">p50 ms</th>
            <th class="num">p95 ms</th>
            <th class="num">p99 ms</th>
            <th class="num">Max ms</th>
            <th class="num">Total ms</th>
          </tr>
        </thead>
        <tbody>{body_rows}</tbody>
      </table>
    </div>"""


def render_metrics_page(user: dict, snap: dict) -> str:
    """Performance page: timings collected since the server started (or since
    the last reset). Admin-only."""
    requests = snap["groups"]["request"]
    functions = snap["groups"]["function"]
    queries = snap["groups"]["query"]

    def find(rows: list, name: str) -> dict:
        for row in rows:
            if row["name"] == name:
                return row
        return {"count": 0, "mean_ms": 0.0, "p95_ms": 0.0}

    login = find(requests, "POST /login")
    find_user = find(functions, "find_user")
    lock_wait = find(queries, "_lock wait")

    total_requests = sum(row["count"] for row in requests)
    total_queries = sum(row["count"] for row in queries if row["name"] != "_lock wait")
    conn = snap["connection"]
    uptime = snap["uptime_seconds"]
    uptime_text = (f"{uptime / 3600:.1f} h" if uptime >= 3600
                   else f"{uptime / 60:.1f} min" if uptime >= 60
                   else f"{uptime:.0f} s")

    body = f"""
<div class="page-head">
  <div>
    <div class="accent-rule"></div>
    <h2>Performance</h2>
    <p class="lead">{total_requests} request{'' if total_requests == 1 else 's'} ·
       {total_queries} quer{'y' if total_queries == 1 else 'ies'} · measured over {uptime_text}</p>
  </div>
  <form class="inline" action="/metrics/reset" method="post"
        onsubmit="return confirm('Clear all collected metrics?');">
    <button class="btn-ghost btn-sm" type="submit">Reset</button>
  </form>
</div>

<div class="kpis">
  <div class="kpi">
    <b>{_ms(conn['last_ms'])} ms</b><span>DB connection open</span>
    <small>{conn['count']} open{'' if conn['count'] == 1 else 's'} since start</small>
  </div>
  <div class="kpi">
    <b>{_ms(login['mean_ms'])} ms</b><span>Login request (mean)</span>
    <small>p95 {_ms(login['p95_ms'])} ms · {login['count']} login{'' if login['count'] == 1 else 's'}</small>
  </div>
  <div class="kpi">
    <b>{_ms(find_user['mean_ms'])} ms</b><span>find_user (mean)</span>
    <small>the login lookup — also runs on every authenticated request</small>
  </div>
  <div class="kpi">
    <b>{_ms(lock_wait['mean_ms'])} ms</b><span>Lock wait (mean)</span>
    <small>p95 {_ms(lock_wait['p95_ms'])} ms</small>
  </div>
  <div class="kpi">
    <b>{snap['lock']['peak_waiting']}</b><span>Peak concurrent</span>
    <small>threads queued for the DB lock</small>
  </div>
</div>

<div class="card">
  <div class="card-head"><h2>HTTP requests</h2></div>
  <p class="hint">End-to-end time inside <code>do_GET</code> / <code>do_POST</code>:
     database work plus HTML rendering.</p>
  {_metric_table(requests, "Route")}
</div>

<div class="card">
  <div class="card-head"><h2>Data functions</h2></div>
  <p class="hint">Time inside each <code>data.py</code> call, including the SQL it runs.</p>
  {_metric_table(functions, "Function")}
</div>

<div class="card">
  <div class="card-head"><h2>SQL statements</h2></div>
  <p class="hint">Time executing each statement, plus <code>_lock wait</code> (highlighted):
     how long threads queued for <code>db._lock</code> before their statement could run.
     All statements share one connection, so this is the contention cost — it stays near
     zero until requests overlap.</p>
  {_metric_table(queries, "Statement")}
</div>
"""
    return render_layout("Performance", body, user, active_nav="metrics")


def render_confirm_request(
    item: dict, professor_name: str, due_date: str, current_items: list[dict], user: dict
) -> str:
    """Confirmation page shown when a request would give a professor a 4th+ active item."""
    rows = "".join(
        f"""
    <tr>
      <td>{html.escape(i['name'])}</td>
      <td>{html.escape(i['assigned_on'])}</td>
      <td>{html.escape(i['due_date'])}{' <span class="badge-overdue">Overdue</span>' if data.is_overdue(i) else ''}</td>
    </tr>"""
        for i in current_items
    )
    body = f"""
<div class="card">
  <h2>Confirm request</h2>
  <p class="muted">
    <strong>{html.escape(professor_name)}</strong> already has {len(current_items)} active item(s).
    Assigning <strong>{html.escape(item['name'])}</strong> would make {len(current_items) + 1}. Continue?
  </p>
  <table>
    <thead><tr><th>Item</th><th>Since</th><th>Due</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <form action="/request" method="post" style="margin-top:16px">
    <input type="hidden" name="item_name" value="{html.escape(item['name'], quote=True)}">
    <input type="hidden" name="professor_name" value="{html.escape(professor_name, quote=True)}">
    <input type="hidden" name="due_date" value="{html.escape(due_date, quote=True)}">
    <input type="hidden" name="confirmed" value="1">
    <div class="actions">
      <button class="btn-primary" type="submit">Confirm anyway</button>
      <a class="btn-ghost btn-sm" href="/"
         style="display:inline-flex;align-items:center;padding:9px 15px;text-decoration:none">Cancel</a>
    </div>
  </form>
</div>
"""
    return render_layout("Confirm request", body, user, active_nav="items")


def _qr_placeholder_svg(code: str) -> str:
    """A decorative, non-functional QR-looking SVG derived from ``code``.

    Fills a 21x21 module grid pseudo-randomly from a hash of the code (so each
    code looks distinct) and stamps the three corner finder patterns. Pure
    string building — no image libraries, matching the app's inline-SVG style.
    """
    n = 21
    # Expand the digest to at least one bit per module.
    digest = hashlib.md5(code.encode()).digest()
    bits = (digest * ((n * n) // len(digest) // 8 + 1))

    def is_finder(r: int, c: int) -> bool:
        # 7x7 finder regions at three corners.
        return (
            (r < 7 and c < 7)
            or (r < 7 and c >= n - 7)
            or (r >= n - 7 and c < 7)
        )

    def finder_on(r: int, c: int) -> bool:
        # Map to local finder coords: filled ring + center 3x3 block.
        lr = r if r < 7 else r - (n - 7)
        lc = c if c < 7 else c - (n - 7)
        if lr in (0, 6) or lc in (0, 6):
            return True
        return 2 <= lr <= 4 and 2 <= lc <= 4

    cells = []
    for r in range(n):
        for c in range(n):
            if is_finder(r, c):
                on = finder_on(r, c)
            else:
                idx = r * n + c
                on = bool(bits[idx // 8] & (1 << (idx % 8)))
            if on:
                cells.append(f'<rect x="{c}" y="{r}" width="1" height="1"/>')
    return (
        f'<svg viewBox="0 0 {n} {n}" xmlns="http://www.w3.org/2000/svg" '
        f'shape-rendering="crispEdges" role="img" aria-label="QR code placeholder">'
        f'<rect width="{n}" height="{n}" fill="#fff"/>'
        f'<g fill="#0f172a">{"".join(cells)}</g></svg>'
    )


def render_return_result(item: dict, code: str, user: dict) -> str:
    """Receipt shown after an item is returned: QR placeholder + pickup code."""
    body = f"""
<div class="card receipt">
  <h2>Item returned</h2>
  <div class="qr-box">{_qr_placeholder_svg(code)}</div>
  <div class="return-code">{html.escape(code)}</div>
  <p class="muted"><strong>{html.escape(item['name'])}</strong> is now available again.</p>
  <div class="actions">
    <a class="btn-primary" href="/"
       style="display:inline-flex;align-items:center;padding:9px 15px;text-decoration:none">Back to Items</a>
    <a class="btn-ghost btn-sm" href="/professors"
       style="display:inline-flex;align-items:center;padding:9px 15px;text-decoration:none">Professors</a>
  </div>
</div>
"""
    return render_layout("Return receipt", body, user, active_nav="items")


def render_row(item: dict, user: dict) -> str:
    """One table row for an item."""
    is_admin = user["role"] == "admin"
    status = item["status"]
    item_id = html.escape(str(item["id"]), quote=True)
    badge = f'<span class="status {status}"><span class="dot"></span>{html.escape(status)}</span>'

    if status == "assigned":
        overdue_html = '<span class="badge-overdue">Overdue</span>' if data.is_overdue(item) else ""
        assigned = (
            f'{html.escape(item["assigned_to"])}{overdue_html}'
            f'<div class="muted">since {html.escape(item["assigned_on"])} '
            f'· due {html.escape(item["due_date"])}</div>'
        )
        if is_admin:
            assign_control = f"""
        <form class="inline" action="/return" method="post">
          <input type="hidden" name="id" value="{item_id}">
          <button class="btn-ghost btn-sm" type="submit">Return</button>
        </form>"""
        else:
            assign_control = f"""
        <button class="btn-ghost btn-sm" type="button" data-id="{item_id}"
                onclick="openReturn(this)">Return</button>"""
    else:
        assigned = '<span class="muted">—</span>'
        assign_control = ""

    desc = (
        f'<div class="muted">{html.escape(item["description"])}</div>'
        if item["description"]
        else ""
    )

    if is_admin:
        toggle_label = "Disable" if status == "available" else "Enable" if status == "disabled" else ""
        toggle_btn = ""
        if toggle_label:
            toggle_btn = f"""
      <form class="inline" action="/toggle-disable" method="post">
        <input type="hidden" name="id" value="{item_id}">
        <button class="btn-ghost btn-sm" type="submit">{toggle_label}</button>
      </form>"""
        admin_actions = f"""
      <button class="btn-ghost btn-sm" type="button"
              data-id="{item_id}"
              data-name="{html.escape(item['name'], quote=True)}"
              data-category="{html.escape(item['category'], quote=True)}"
              data-description="{html.escape(item['description'], quote=True)}"
              onclick="openEdit(this)">Edit</button>
      {toggle_btn}
      <form class="inline" action="/remove" method="post"
            onsubmit="return confirm('Remove this item?');">
        <input type="hidden" name="id" value="{item_id}">
        <button class="btn-danger btn-sm" type="submit">Remove</button>
      </form>"""
    else:
        admin_actions = ""

    return f"""
<tr data-name="{html.escape(item['name'].lower(), quote=True)}" data-assigned="{html.escape(item['assigned_to'], quote=True)}">
  <td><strong>{html.escape(item['name'])}</strong>{desc}</td>
  <td>{html.escape(item['category']) or '<span class="muted">—</span>'}</td>
  <td>{badge}</td>
  <td>{assigned}</td>
  <td>
    <div class="actions" style="justify-content:flex-end; flex-wrap:nowrap">
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
        <input name="username" required autofocus autocomplete="username" placeholder="admin or DGarcia"></div>
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
