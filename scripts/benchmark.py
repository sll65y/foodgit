"""Small, read-only HTTP throughput check against the local prototype."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
from statistics import median
from time import perf_counter
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.requests < 1 or args.workers < 1:
        parser.error("requests and workers must be positive")
    base = f"http://127.0.0.1:{args.port}/api"
    login = Request(base + "/auth/login", b'{"username":"demo","password":"food-demo"}',
                    {"Content-Type": "application/json"})
    with urlopen(login, timeout=5) as response:
        headers = {"Authorization": "Bearer " + json.load(response)["token"]}
    for path in ("/dishes?page=2&size=6", "/stats?days=7"):
        def fetch(_):
            start = perf_counter()
            try:
                with urlopen(Request(base + path, headers=headers), timeout=5) as res:
                    res.read()
            except OSError:
                return None
            return (perf_counter() - start) * 1000

        start = perf_counter()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            results = sorted(r for r in pool.map(fetch, range(args.requests)) if r is not None)
        elapsed = perf_counter() - start
        print(json.dumps({
            "path": path, "requests": args.requests, "workers": args.workers,
            "errors": args.requests - len(results), "success_rps": round(len(results) / elapsed, 1),
            "p50_ms": round(median(results), 2) if results else None,
            "p95_ms": round(results[math.ceil(.95 * len(results)) - 1], 2) if results else None,
        }))


if __name__ == "__main__":
    main()
