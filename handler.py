"""HTTP request handler — all GET/POST routing.

Reads state from and mutates the ``data`` module; renders responses with the
``views`` module.
"""

from __future__ import annotations

from datetime import date
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

import data
import views


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
        if username and username in data.USERS:
            return {"name": username, "role": data.USERS[username]["role"]}
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
        else:
            self._send_html(404, views.render_404())

    def do_POST(self):
        url = urlparse(self.path)
        form = self._read_form()
        user = self.current_user()

        if url.path == "/login":
            username = form.get("username", "").strip()
            password = form.get("password", "")
            account = data.USERS.get(username)
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
        )
        if url.path in admin_routes and user["role"] != "admin":
            self._redirect("/")
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

            if error:
                values = {
                    "id": item_id,
                    "name": name,
                    "category": category,
                    "description": description,
                }
                self._send_html(200, views.render_index(user, add_error=error, add_values=values))
                return

            if name and category in data.CATEGORIES:
                data.add_item(item_id, name, category, description)
            self._redirect("/")

        elif url.path == "/edit":
            item = data.find_item(form.get("id", ""))
            if item:
                name = form.get("name", "").strip()
                category = form.get("category", "").strip()
                if name:
                    item["name"] = name
                if category in data.CATEGORIES:
                    item["category"] = category
                item["description"] = form.get("description", "").strip()
            self._redirect("/")

        elif url.path == "/remove":
            item = data.find_item(form.get("id", ""))
            if item:
                data.ITEMS.remove(item)
            self._redirect("/")

        elif url.path == "/toggle-disable":
            item = data.find_item(form.get("id", ""))
            if item and item["status"] in ("available", "disabled"):
                item["status"] = "disabled" if item["status"] == "available" else "available"
            self._redirect("/")

        elif url.path == "/return":
            item = data.find_item(form.get("id", ""))
            if item:
                item["status"] = "available"
                item["assigned_to"] = ""
                item["assigned_on"] = ""
                item["due_date"] = ""
            self._redirect("/")

        elif url.path == "/professors/add":
            name = form.get("name", "").strip()
            if name:
                data.add_professor(name, form.get("department", "").strip())
            self._redirect("/professors")

        elif url.path == "/professors/edit":
            prof = data.find_professor(int(form.get("id", 0) or 0))
            if prof:
                name = form.get("name", "").strip()
                if name:
                    prof["name"] = name
                prof["department"] = form.get("department", "").strip()
            self._redirect("/professors")

        elif url.path == "/professors/remove":
            prof = data.find_professor(int(form.get("id", 0) or 0))
            if prof:
                has_active = any(
                    i["assigned_to"] == prof["name"] and i["status"] == "assigned"
                    for i in data.ITEMS
                )
                if has_active:
                    self._send_html(200, views.render_professors_page(
                        user,
                        professors_error="Cannot remove: this professor has active assigned items.",
                    ))
                    return
                data.PROFESSORS.remove(prof)
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
                item = next(
                    (i for i in data.ITEMS if i["name"] == item_name and i["status"] == "available"),
                    None,
                )
                if not item:
                    error = "Select an available item from the list."

            professor = None
            if not error:
                professor = next((p for p in data.PROFESSORS if p["name"] == professor_name), None)
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

            current_items = [
                i for i in data.ITEMS
                if i["assigned_to"] == professor["name"] and i["status"] == "assigned"
            ]
            if len(current_items) >= 3 and not confirmed:
                self._send_html(
                    200,
                    views.render_confirm_request(item, professor["name"], due_date, current_items, user),
                )
                return

            item["status"] = "assigned"
            item["assigned_to"] = professor["name"]
            item["assigned_on"] = today_iso
            item["due_date"] = due_date
            self._redirect("/")

        else:
            self._send_html(404, views.render_404())
