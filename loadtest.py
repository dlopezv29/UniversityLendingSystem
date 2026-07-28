"""Concurrent load generator, so the /metrics page has contention to show.

The lock-wait metric stays at ~0 ms while requests arrive one at a time. Run
this against a live server to make threads actually queue for ``db._lock``:

    python3 app.py                      # terminal 1
    python3 loadtest.py -c 20 -n 400    # terminal 2

Then open http://localhost:8000/metrics and look at "Lock wait" and
"Peak concurrent". Raise ``-c`` to push contention up.

Client-side latency is printed here; server-side timings live on /metrics.
"""

from __future__ import annotations

import argparse
import statistics
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

# Read-only paths: hammering these is safe to repeat.
PATHS = ["/", "/professors", "/"]


def login(base: str, username: str, password: str) -> str:
    """Sign in and return the session cookie value."""
    body = urllib.parse.urlencode({"username": username, "password": password}).encode()
    request = urllib.request.Request(base + "/login", data=body, method="POST")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    opener = urllib.request.build_opener(NoRedirect)
    try:
        response = opener.open(request)
        headers = response.headers
    except urllib.error.HTTPError as exc:
        headers = exc.headers

    cookie = headers.get("Set-Cookie", "")
    if "session=" not in cookie:
        raise SystemExit("Login failed — check the username and password.")
    return cookie.split("session=", 1)[1].split(";", 1)[0]


def worker(base: str, token: str, count: int, out: list, errors: list) -> None:
    opener = urllib.request.build_opener()
    for i in range(count):
        path = PATHS[i % len(PATHS)]
        request = urllib.request.Request(base + path)
        request.add_header("Cookie", f"session={token}")
        start = time.perf_counter()
        try:
            with opener.open(request) as response:
                response.read()
        except Exception as exc:  # noqa: BLE001 - report, don't stop the run
            errors.append(repr(exc))
            continue
        out.append(time.perf_counter() - start)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-c", "--concurrency", type=int, default=20,
                        help="parallel threads (default: 20)")
    parser.add_argument("-n", "--requests", type=int, default=400,
                        help="total requests (default: 400)")
    parser.add_argument("-u", "--url", default="http://localhost:8000",
                        help="base URL (default: http://localhost:8000)")
    parser.add_argument("--user", default="admin")
    parser.add_argument("--password", default="password")
    args = parser.parse_args()

    base = args.url.rstrip("/")
    token = login(base, args.user, args.password)

    per_thread = max(1, args.requests // args.concurrency)
    total = per_thread * args.concurrency

    samples: list = []
    errors: list = []
    threads = [
        threading.Thread(target=worker, args=(base, token, per_thread, samples, errors))
        for _ in range(args.concurrency)
    ]

    print(f"{total} requests over {args.concurrency} threads -> {base}")
    started = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    elapsed = time.perf_counter() - started

    if not samples:
        raise SystemExit(f"No successful requests. First error: {errors[0]}")

    ordered = sorted(samples)

    def percentile(fraction: float) -> float:
        return ordered[int(round(fraction * (len(ordered) - 1)))] * 1000

    print(f"\nwall time     {elapsed:.2f} s")
    print(f"throughput    {len(samples) / elapsed:.0f} req/s")
    print(f"ok / failed   {len(samples)} / {len(errors)}")
    print("\nclient-side latency (ms)")
    print(f"  mean  {statistics.mean(ordered) * 1000:8.2f}")
    print(f"  p50   {percentile(0.50):8.2f}")
    print(f"  p95   {percentile(0.95):8.2f}")
    print(f"  p99   {percentile(0.99):8.2f}")
    print(f"  max   {ordered[-1] * 1000:8.2f}")
    if errors:
        print(f"\nfirst error: {errors[0]}")
    print(f"\nServer-side breakdown: {base}/metrics")


if __name__ == "__main__":
    main()
