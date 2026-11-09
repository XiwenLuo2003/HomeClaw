"""Dependency-free HTTP load generator for deployed HomeClaw components.

The script performs no work unless a deployment operator explicitly runs it.
Output paths are restricted to the HomeClaw repository.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from homeclaw.eval.performance import percentile  # noqa: E402


def request_once(url: str, payload: bytes, timeout: float) -> dict:
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    status = 0
    error = ""
    response_bytes = 0
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            response_bytes = len(response.read())
    except urllib.error.HTTPError as exc:
        status = exc.code
        error = f"HTTPError:{exc.code}"
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    return {
        "status": status,
        "error": error,
        "latency_ms": (time.perf_counter() - started) * 1000.0,
        "response_bytes": response_bytes,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.requests <= 0 or args.concurrency <= 0:
        raise SystemExit("requests and concurrency must be positive")
    payload_path = args.payload if args.payload.is_absolute() else ROOT / args.payload
    payload = payload_path.read_bytes()

    started = time.perf_counter()
    results = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [
            executor.submit(request_once, args.url, payload, args.timeout)
            for _ in range(args.requests)
        ]
        for future in as_completed(futures):
            results.append(future.result())
    duration = time.perf_counter() - started
    latencies = [item["latency_ms"] for item in results]
    successes = [item for item in results if 200 <= item["status"] < 300]
    report = {
        "provenance": {
            "url": args.url,
            "payload_file": str(payload_path),
            "requests": args.requests,
            "concurrency": args.concurrency,
            "timeout_seconds": args.timeout,
            "warning": "Endpoint/model/container versions must be recorded separately for comparability."
        },
        "summary": {
            "duration_seconds": duration,
            "throughput_qps": len(results) / duration if duration else 0.0,
            "success_rate": len(successes) / len(results),
            "latency_average_ms": statistics.mean(latencies),
            "latency_p50_ms": percentile(latencies, 0.50),
            "latency_p95_ms": percentile(latencies, 0.95),
            "latency_max_ms": max(latencies),
        },
        "errors": [item["error"] for item in results if item["error"]],
    }
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output = output.resolve()
    if ROOT not in output.parents:
        raise SystemExit("output must remain inside the HomeClaw repository")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
