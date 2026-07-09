"""University Equipment Lending — entry point.

Run with ``python3 app.py`` and open http://localhost:8000.
Application code lives in:
  data.py     hardcoded state + helpers
  views.py    HTML rendering
  handler.py  HTTP routing
"""

from http.server import ThreadingHTTPServer

from handler import Handler

HOST = "localhost"
PORT = 8000


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
