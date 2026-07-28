"""University Equipment Lending — entry point.

Run with ``python3 app.py`` and open http://localhost:8000.
Application code lives in:
  db.py       SQLite connection, schema, seed data
  data.py     data access (items, professors, accounts) + helpers
  views.py    HTML rendering
  handler.py  HTTP routing
"""

from http.server import ThreadingHTTPServer

import db
from handler import Handler

HOST = "localhost"
PORT = 8000


def main():
    db.init()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"University Equipment Lending running at http://{HOST}:{PORT}")
    print(f"Database: {db.DB_PATH} — data persists across restarts.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
