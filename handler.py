"""HTTP request handler — all GET/POST routing.

Reads state from and mutates the ``data`` module; renders responses with the
``views`` module.
"""

from __future__ import annotations

import time
from datetime import date
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

import data
import metrics
import views

# Paths that get their own metric label. Anything else is folded into "other",
# so a flood of 404s cannot grow the metrics table without bound.
KNOWN_PATHS = {
    "/", "/login", "/logout", "/professors", "/metrics", "/metrics/reset",
    "/add", "/edit", "/remove", "/toggle-disable", "/return", "/request",
    "/professors/add", "/professors/edit", "/professors/remove",
}


class Handler(BaseHTTPRequestHandler):
    # --- helpers --------------------------------------------------------
    def _send_html(self, code: int, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

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
        username = data.SESSIONS.get(morsel.value)
        account = data.find_user(username) if username else None
        if account:
            return {
                "name": account["name"],
                "role": account["role"],
                "professor": account["professor"],
            }
        return None

    def log_message(self, fmt, *args):  # quieter console
        return

    def _metric_label(self, verb: str) -> str:
        path = urlparse(self.path).path
        return f"{verb} {path if path in KNOWN_PATHS else 'other'}"

    # --- routes ---------------------------------------------------------
    def do_GET(self):
        """Time the whole request, then route it."""
        start = time.perf_counter()
        try:
            self._route_get()
        finally:
            metrics.record("request", self._metric_label("GET"),
                           time.perf_counter() - start)

    def do_POST(self):
        """Time the whole request, then route it."""
        start = time.perf_counter()
        try:
            self._route_post()
        finally:
            metrics.record("request", self._metric_label("POST"),
                           time.perf_counter() - start)

    def _route_get(self):
        url = urlparse(self.path)
        user = self.current_user()

        if url.path == "/login":
            if user:
                self._redirect("/")
            else:
                error = parse_qs(url.query).get("error", ["0"])[0] == "1"
                self._send_html(200, views.render_login(error))
            return

        if not user:
            self._redirect("/login")
            return

        if url.path == "/":
            qs = parse_qs(url.query)
            category_filter = qs.get("category", [""])[0]
            if category_filter not in data.CATEGORIES:
                category_filter = ""
            overdue_only = qs.get("overdue", [""])[0] == "1"
            self._send_html(200, views.render_index(user, category_filter, overdue_only))
        elif url.path == "/professors":
            if user["role"] != "admin":
                self._redirect("/")
                return
            self._send_html(200, views.render_professors_page(user))
        elif url.path == "/metrics":
            if user["role"] != "admin":
                self._redirect("/")
                return
            self._send_html(200, views.render_metrics_page(user, metrics.snapshot()))
        else:
            self._send_html(404, views.render_404())

    def _route_post(self):
        url = urlparse(self.path)
        form = self._read_form()
        user = self.current_user()

        if url.path == "/login":
            username = form.get("username", "").strip()
            password = form.get("password", "")
            account = data.find_user(username)
            if account and account["password"] == password:
                token = data.new_token()
                data.SESSIONS[token] = username
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
                    data.SESSIONS.pop(morsel.value, None)
            self._redirect("/login", cookie="session=; HttpOnly; Path=/; Max-Age=0")
            return

        # All remaining routes require authentication.
        if not user:
            self._redirect("/login")
            return

        # Admin-only mutations.
        admin_routes = (
            "/add", "/edit", "/remove", "/toggle-disable", "/request",
            "/professors/add", "/professors/edit", "/professors/remove",
            "/metrics/reset",
        )
        if url.path in admin_routes and user["role"] != "admin":
            self._redirect("/")
            return

        if url.path == "/metrics/reset":
            metrics.reset()
            self._redirect("/metrics")
            return

        if url.path == "/add":
            item_id = form.get("id", "").strip()
            name = form.get("name", "").strip()
            category = form.get("category", "").strip()
            description = form.get("description", "").strip()

            error = None
            if not item_id:
                error = "ID is required."
            elif not data.valid_item_id(item_id):
                error = "ID may only contain letters, numbers, dashes, and underscores."
            elif data.find_item(item_id):
                error = f"ID '{item_id}' is already in use."

            if not error and name and category in data.CATEGORIES:
                # The database has the final say on uniqueness, so a second
                # request that slipped past the check above still loses here.
                if data.add_item(item_id, name, category, description) is None:
                    error = f"ID '{item_id}' is already in use."

            if error:
                values = {
                    "id": item_id,
                    "name": name,
                    "category": category,
                    "description": description,
                }
                self._send_html(200, views.render_index(user, add_error=error, add_values=values))
                return

            self._redirect("/")

        elif url.path == "/edit":
            item_id = form.get("id", "")
            if data.find_item(item_id):
                data.update_item(
                    item_id,
                    form.get("name", "").strip(),
                    form.get("category", "").strip(),
                    form.get("description", "").strip(),
                )
            self._redirect("/")

        elif url.path == "/remove":
            data.delete_item(form.get("id", ""))
            self._redirect("/")

        elif url.path == "/toggle-disable":
            item = data.find_item(form.get("id", ""))
            if item and item["status"] in ("available", "disabled"):
                new_status = "disabled" if item["status"] == "available" else "available"
                data.set_item_status(item["id"], new_status)
            self._redirect("/")

        elif url.path == "/return":
            item = data.find_item(form.get("id", ""))
            if item:
                is_admin = user["role"] == "admin"
                code_ok = is_admin or form.get("code", "") == "1234"
                if code_ok:
                    data.return_item(item["id"])
                    item = data.find_item(item["id"])
                    code = data.generate_return_code()
                    self._send_html(200, views.render_return_result(item, code, user))
                    return
                self._send_html(200, views.render_index(
                    user, return_error="Code not matched", return_error_id=item["id"]))
                return
            self._redirect("/")

        elif url.path == "/professors/add":
            id_card = form.get("id_card", "").strip()
            name = form.get("name", "").strip()
            department = form.get("department", "").strip()

            error = None
            if not id_card:
                error = "ID Card is required."
            elif not data.valid_id_card(id_card):
                error = "ID Card may only contain letters, numbers, dashes, and underscores."
            elif data.find_professor_by_id_card(id_card):
                error = f"ID Card '{id_card}' is already in use."

            if not error and name:
                if data.add_professor(name, department, id_card) is None:
                    error = f"ID Card '{id_card}' is already in use."

            if error:
                values = {"id_card": id_card, "name": name, "department": department}
                self._send_html(200, views.render_professors_page(
                    user, add_error=error, add_values=values))
                return

            self._redirect("/professors")

        elif url.path == "/professors/edit":
            prof = data.find_professor(int(form.get("id", 0) or 0))
            if prof:
                id_card = form.get("id_card", "").strip()
                name = form.get("name", "").strip()

                error = None
                if not id_card:
                    error = "ID Card is required."
                elif not data.valid_id_card(id_card):
                    error = "ID Card may only contain letters, numbers, dashes, and underscores."
                else:
                    existing = data.find_professor_by_id_card(id_card)
                    if existing and existing["id"] != prof["id"]:
                        error = f"ID Card '{id_card}' is already in use."

                if not error:
                    ok = data.update_professor(
                        prof["id"], id_card, name, form.get("department", "").strip()
                    )
                    if not ok:
                        error = f"ID Card '{id_card}' is already in use."

                if error:
                    self._send_html(200, views.render_professors_page(user, professors_error=error))
                    return
            self._redirect("/professors")

        elif url.path == "/professors/remove":
            prof = data.find_professor(int(form.get("id", 0) or 0))
            if prof:
                has_active = data.professor_active_item_count(prof["id"]) > 0
                if has_active:
                    self._send_html(200, views.render_professors_page(
                        user,
                        professors_error="Cannot remove: this professor has active assigned items.",
                    ))
                    return
                data.delete_professor(prof["id"])
            self._redirect("/professors")

        elif url.path == "/request":
            item_name = form.get("item_name", "").strip()
            professor_name = form.get("professor_name", "").strip()
            due_date = form.get("due_date", "").strip()
            confirmed = form.get("confirmed", "") == "1"
            today_iso = date.today().isoformat()

            error = None
            if not due_date or due_date < today_iso:
                error = "Return date must be today or later."

            item = None
            if not error:
                item = data.find_available_item_by_name(item_name)
                if not item:
                    error = "Select an available item from the list."

            professor = None
            if not error:
                professor = data.find_professor_by_name(professor_name)
                if not professor:
                    error = "Select an existing professor from the list, or add them first."

            if error:
                values = {
                    "item_name": item_name,
                    "professor_name": professor_name,
                    "due_date": due_date or today_iso,
                }
                self._send_html(200, views.render_index(user, request_error=error, request_values=values))
                return

            current_items = data.items_assigned_to(professor["id"])
            if len(current_items) >= 3 and not confirmed:
                self._send_html(
                    200,
                    views.render_confirm_request(item, professor["name"], due_date, current_items, user),
                )
                return

            data.assign_item(item["id"], professor["id"], today_iso, due_date)
            self._redirect("/")

        else:
            self._send_html(404, views.render_404())
