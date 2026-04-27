#!/usr/bin/env python3
"""
scripts/benchmark_tiles.py
==========================
Benchmark the WebMet25 tile endpoint under sequential and concurrent load.

Usage
-----
    python scripts/benchmark_tiles.py \\
        --host localhost \\
        --port 8080 \\
        --cog-ids 1 2 3 4 5 \\
        --concurrency 20 \\
        --zoom 7

The script runs TWO passes automatically:
    Pass 1 — baseline:  concurrency=1  (sequential, warms Redis L2 cache)
    Pass 2 — parallel:  concurrency=N  (the value you supplied)

Between passes the script does NOT flush the cache intentionally —
Pass 2 measures warm-cache parallel throughput, which is the
production hot-path.  If you want cold-cache numbers, restart the
redis container before running.

Getting valid COG IDs
---------------------
Run the following command on the server to get IDs of available COGs:

    docker compose exec radar_db-gl psql \\
        -U $POSTGRES_USER \\
        -d $POSTGRES_DB \\
        -c "SELECT id FROM radar_cogs WHERE status='available' LIMIT 10;"

Then pass those IDs to --cog-ids.

Dependencies
------------
    pip install aiohttp          # only extra dependency needed

Python stdlib only otherwise (asyncio, argparse, statistics, time, itertools).

Tile URL pattern
----------------
    GET /api/v1/tiles/{cog_id}/{z}/{x}/{y}.png

The script generates a representative set of (x, y) tile coordinates
for the requested zoom level that cover Argentina's bounding box
(roughly lat -55 to -22, lon -74 to -53).  This avoids hammering a
single tile coordinate while keeping the coordinate set deterministic
and reproducible across runs.
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import math
import statistics
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Tuple

try:
    import aiohttp
except ImportError:
    print(
        "ERROR: aiohttp is not installed.\n"
        "Install it with:  pip install aiohttp",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Geo helpers — convert lat/lon bounding box to tile (x, y) coordinates
# ---------------------------------------------------------------------------

def _lon_to_tile_x(lon_deg: float, zoom: int) -> int:
    n = 2**zoom
    return int((lon_deg + 180.0) / 360.0 * n)


def _lat_to_tile_y(lat_deg: float, zoom: int) -> int:
    lat_rad = math.radians(lat_deg)
    n = 2**zoom
    return int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)


def _tiles_for_bbox(
    west: float,
    south: float,
    east: float,
    north: float,
    zoom: int,
) -> List[Tuple[int, int]]:
    """Return all (x, y) tile coordinates that cover the given bounding box."""
    x_min = _lon_to_tile_x(west, zoom)
    x_max = _lon_to_tile_x(east, zoom)
    y_min = _lat_to_tile_y(north, zoom)  # note: y axis is flipped
    y_max = _lat_to_tile_y(south, zoom)

    tiles = [
        (x, y)
        for x in range(x_min, x_max + 1)
        for y in range(y_min, y_max + 1)
    ]
    return tiles


# Argentina bounding box (generous, covers all ~15 radars)
ARGENTINA_BBOX = dict(west=-74.0, south=-55.0, east=-53.0, north=-22.0)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RequestResult:
    url: str
    status: int
    elapsed_ms: float
    error: str | None = None


@dataclass
class RunStats:
    label: str
    concurrency: int
    total_requests: int
    wall_time_s: float
    results: List[RequestResult] = field(default_factory=list)

    # Computed after collection
    ok_count: int = 0
    error_count: int = 0
    latencies_ms: List[float] = field(default_factory=list)

    def compute(self) -> None:
        self.ok_count = sum(
            1 for r in self.results if r.error is None and r.status == 200
        )
        self.error_count = len(self.results) - self.ok_count
        # Always include all latencies (errors included) so we never show 0.0
        self.latencies_ms = [r.elapsed_ms for r in self.results]

    @property
    def requests_per_second(self) -> float:
        return self.total_requests / self.wall_time_s if self.wall_time_s > 0 else 0.0

    @property
    def p50(self) -> float:
        return statistics.median(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def p95(self) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_lat = sorted(self.latencies_ms)
        idx = max(0, int(len(sorted_lat) * 0.95) - 1)
        return sorted_lat[idx]

    @property
    def mean(self) -> float:
        return statistics.mean(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def min_lat(self) -> float:
        return min(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def max_lat(self) -> float:
        return max(self.latencies_ms) if self.latencies_ms else 0.0

    def error_summary(self, max_samples: int = 5) -> str:
        """Return a short human-readable summary of what went wrong."""
        errors = [r for r in self.results if r.error is not None or r.status != 200]
        if not errors:
            return ""

        # Count by error message / status
        counter: Counter = Counter()
        for r in errors:
            if r.error:
                # Truncate long exception strings to first 120 chars
                key = r.error[:120]
            else:
                key = f"HTTP {r.status}"
            counter[key] += 1

        lines = [f"  Error breakdown ({len(errors)} total):"]
        for msg, count in counter.most_common(10):
            lines.append(f"    {count:>5}×  {msg}")

        # Show a few example URLs so we can verify the path is right
        lines.append(f"  Sample URLs that failed:")
        for r in errors[:max_samples]:
            lines.append(f"    {r.url}  →  status={r.status}  err={r.error}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core async benchmark logic
# ---------------------------------------------------------------------------

async def _fetch(
    session: aiohttp.ClientSession,
    url: str,
    semaphore: asyncio.Semaphore,
) -> RequestResult:
    """Fetch a single tile URL, respecting the semaphore concurrency limit."""
    async with semaphore:
        start = time.perf_counter()
        try:
            async with session.get(url) as resp:
                await resp.read()  # consume body so connection is returned
                elapsed_ms = (time.perf_counter() - start) * 1000
                return RequestResult(url=url, status=resp.status, elapsed_ms=elapsed_ms)
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return RequestResult(
                url=url, status=0, elapsed_ms=elapsed_ms, error=str(exc)
            )


async def run_benchmark(
    urls: List[str],
    concurrency: int,
    label: str,
    timeout_s: float = 30.0,
    auth: aiohttp.BasicAuth | None = None,
) -> RunStats:
    """Run a full benchmark pass and return a RunStats object."""
    semaphore = asyncio.Semaphore(concurrency)
    connector = aiohttp.TCPConnector(limit=concurrency + 4)
    timeout = aiohttp.ClientTimeout(total=timeout_s)

    print(f"\n  Running pass: {label}  (concurrency={concurrency}, {len(urls)} requests)")

    results: List[RequestResult] = []
    wall_start = time.perf_counter()

    async with aiohttp.ClientSession(connector=connector, timeout=timeout, auth=auth) as session:
        tasks = [_fetch(session, url, semaphore) for url in urls]

        # Progress dots — one dot per 10% of requests
        chunk_size = max(1, len(tasks) // 10)
        completed = 0
        print("  Progress: [", end="", flush=True)
        for chunk in _chunked(tasks, chunk_size):
            chunk_results = await asyncio.gather(*chunk)
            results.extend(chunk_results)
            completed += len(chunk_results)
            print("█", end="", flush=True)
        print(f"]  {completed}/{len(tasks)} done")

    wall_time_s = time.perf_counter() - wall_start

    stats = RunStats(
        label=label,
        concurrency=concurrency,
        total_requests=len(urls),
        wall_time_s=wall_time_s,
        results=results,
    )
    stats.compute()
    return stats


def _chunked(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


# ---------------------------------------------------------------------------
# URL generation
# ---------------------------------------------------------------------------

def build_urls(base_url: str, cog_ids: List[int], zoom: int) -> List[str]:
    """
    Build a list of tile URLs for all cog_ids × all tiles covering Argentina
    at the requested zoom level.
    """
    tiles = _tiles_for_bbox(**ARGENTINA_BBOX, zoom=zoom)
    if not tiles:
        print(
            f"WARNING: No tiles found for Argentina bbox at zoom={zoom}. "
            "Try a lower zoom level.",
            file=sys.stderr,
        )
        sys.exit(1)

    urls = [
        f"{base_url}/api/v1/tiles/{cog_id}/{zoom}/{x}/{y}.png"
        for cog_id, (x, y) in itertools.product(cog_ids, tiles)
    ]
    return urls


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _fmt(value: float, unit: str = "ms", width: int = 8) -> str:
    return f"{value:>{width}.1f} {unit}"


def print_run_stats(stats: RunStats) -> None:
    print(f"\n  ┌─ {stats.label} (c={stats.concurrency})")
    print(f"  │  Total requests : {stats.total_requests}")
    print(f"  │  HTTP 200 OK    : {stats.ok_count}")
    print(f"  │  Errors         : {stats.error_count}")
    print(f"  │  Wall time      : {stats.wall_time_s:.2f} s")
    print(f"  │  Throughput     : {stats.requests_per_second:.1f} req/s")
    print(f"  │  Latency min    : {_fmt(stats.min_lat)}")
    print(f"  │  Latency p50    : {_fmt(stats.p50)}")
    print(f"  │  Latency mean   : {_fmt(stats.mean)}")
    print(f"  │  Latency p95    : {_fmt(stats.p95)}")
    print(f"  └─ Latency max    : {_fmt(stats.max_lat)}")

    # Always print error details if anything went wrong
    summary = stats.error_summary()
    if summary:
        print()
        print(summary)


def print_comparison(baseline: RunStats, parallel: RunStats) -> None:
    print("\n" + "=" * 60)
    print("  COMPARISON SUMMARY")
    print("=" * 60)

    header = f"  {'Metric':<28} {'Baseline (c=1)':>16} {'Parallel (c=N)':>16} {'Ratio':>10}"
    print(header)
    print("  " + "-" * 72)

    def row(
        label: str,
        b_val: float,
        p_val: float,
        unit: str = "ms",
        lower_is_better: bool = True,
    ) -> None:
        if b_val == 0:
            ratio_str = "  N/A"
        else:
            ratio = p_val / b_val
            if lower_is_better:
                marker = "✓" if ratio <= 1.0 else "✗"
            else:
                marker = "✓" if ratio >= 1.0 else "✗"
            ratio_str = f"{ratio:>8.2f}x {marker}"
        print(
            f"  {label:<28} {b_val:>12.1f} {unit}  {p_val:>12.1f} {unit}  {ratio_str}"
        )

    row("Wall time",    baseline.wall_time_s,        parallel.wall_time_s,        unit="s ",  lower_is_better=True)
    row("Throughput",   baseline.requests_per_second, parallel.requests_per_second, unit="r/s", lower_is_better=False)
    row("Latency p50",  baseline.p50,                 parallel.p50,                unit="ms",  lower_is_better=True)
    row("Latency mean", baseline.mean,                parallel.mean,               unit="ms",  lower_is_better=True)
    row("Latency p95",  baseline.p95,                 parallel.p95,                unit="ms",  lower_is_better=True)
    row("Latency max",  baseline.max_lat,             parallel.max_lat,            unit="ms",  lower_is_better=True)

    print("  " + "-" * 72)
    print(f"  {'HTTP 200 OK':<28} {baseline.ok_count:>13}     {parallel.ok_count:>13}")
    print(f"  {'Errors':<28} {baseline.error_count:>13}     {parallel.error_count:>13}")
    print("=" * 60)

    if baseline.wall_time_s > 0 and parallel.wall_time_s > 0:
        speedup = baseline.wall_time_s / parallel.wall_time_s
        print(f"\n  ★  Overall wall-time speedup: {speedup:.2f}x")
        if parallel.error_count > 0:
            error_rate = parallel.error_count / parallel.total_requests * 100
            print(f"  ⚠  Error rate at c={parallel.concurrency}: {error_rate:.1f}%")

    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark the WebMet25 /api/v1/tiles/ endpoint.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--host",
        default="localhost",
        help="Host to benchmark against (default: localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port (default: 8080, i.e. Caddy entry point)",
    )
    parser.add_argument(
        "--cog-ids",
        nargs="+",
        type=int,
        required=True,
        metavar="ID",
        help="One or more RadarCOG IDs to include in the benchmark",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=20,
        help="Max concurrent requests for the parallel pass (default: 20)",
    )
    parser.add_argument(
        "--zoom",
        type=int,
        default=7,
        help="Tile zoom level (default: 7 — ~12 tiles cover Argentina)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Per-request timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--scheme",
        choices=["http", "https"],
        default="http",
        help="URL scheme (default: http)",
    )
    parser.add_argument(
        "--username",
        default=None,
        help="HTTP Basic Auth username (required when targeting Caddy on port 8080)",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="HTTP Basic Auth password",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    base_url = f"{args.scheme}://{args.host}:{args.port}"
    urls = build_urls(base_url, args.cog_ids, args.zoom)

    auth: aiohttp.BasicAuth | None = None
    if args.username:
        auth = aiohttp.BasicAuth(args.username, args.password or "")

    print("=" * 60)
    print("  WebMet25 Tile Benchmark")
    print("=" * 60)
    print(f"  Target         : {base_url}")
    print(f"  Auth           : {'Basic (' + args.username + ')' if auth else 'None (no credentials)'}")  
    print(f"  COG IDs        : {args.cog_ids}")
    print(f"  Zoom level     : {args.zoom}")
    print(f"  Tiles/COG      : {len(_tiles_for_bbox(**ARGENTINA_BBOX, zoom=args.zoom))}")
    print(f"  Total URLs     : {len(urls)}")
    print(f"  Baseline pass  : concurrency=1")
    print(f"  Parallel pass  : concurrency={args.concurrency}")

    # Pass 1 — baseline (sequential, also warms Redis L2)
    baseline = asyncio.run(
        run_benchmark(
            urls,
            concurrency=1,
            label="Baseline (sequential)",
            timeout_s=args.timeout,
            auth=auth,
        )
    )
    print_run_stats(baseline)

    # Pass 2 — parallel
    parallel = asyncio.run(
        run_benchmark(
            urls,
            concurrency=args.concurrency,
            label=f"Parallel (c={args.concurrency})",
            timeout_s=args.timeout,
            auth=auth,
        )
    )
    print_run_stats(parallel)

    # Comparison table
    print_comparison(baseline, parallel)


if __name__ == "__main__":
    main()
# #!/usr/bin/env python3
# """
# scripts/benchmark_tiles.py
# ==========================
# Benchmark the WebMet25 tile endpoint under sequential and concurrent load.

# Usage
# -----
#     python scripts/benchmark_tiles.py \\
#         --host localhost \\
#         --port 8080 \\
#         --cog-ids 1 2 3 4 5 \\
#         --concurrency 20 \\
#         --zoom 7

# The script runs TWO passes automatically:
#     Pass 1 — baseline:  concurrency=1  (sequential, warms Redis L2 cache)
#     Pass 2 — parallel:  concurrency=N  (the value you supplied)

# Between passes the script does NOT flush the cache intentionally —
# Pass 2 measures warm-cache parallel throughput, which is the
# production hot-path.  If you want cold-cache numbers, restart the
# redis container before running.

# Getting valid COG IDs
# ---------------------
# Run the following command on the server to get IDs of available COGs:

#     docker compose exec radar_db-gl psql \\
#         -U $POSTGRES_USER \\
#         -d $POSTGRES_DB \\
#         -c "SELECT id FROM radar_cogs WHERE status='available' LIMIT 10;"

# Then pass those IDs to --cog-ids.

# Dependencies
# ------------
#     pip install aiohttp          # only extra dependency needed

# Python stdlib only otherwise (asyncio, argparse, statistics, time, itertools).

# Tile URL pattern
# ----------------
#     GET /api/v1/tiles/{cog_id}/{z}/{x}/{y}.png

# The script generates a representative set of (x, y) tile coordinates
# for the requested zoom level that cover Argentina's bounding box
# (roughly lat -55 to -22, lon -74 to -53).  This avoids hammering a
# single tile coordinate while keeping the coordinate set deterministic
# and reproducible across runs.
# """

# from __future__ import annotations

# import argparse
# import asyncio
# import itertools
# import math
# import statistics
# import sys
# import time
# from dataclasses import dataclass, field
# from typing import List, Tuple

# try:
#     import aiohttp
# except ImportError:
#     print(
#         "ERROR: aiohttp is not installed.\n"
#         "Install it with:  pip install aiohttp",
#         file=sys.stderr,
#     )
#     sys.exit(1)


# # ---------------------------------------------------------------------------
# # Geo helpers — convert lat/lon bounding box to tile (x, y) coordinates
# # ---------------------------------------------------------------------------

# def _lon_to_tile_x(lon_deg: float, zoom: int) -> int:
#     n = 2**zoom
#     return int((lon_deg + 180.0) / 360.0 * n)


# def _lat_to_tile_y(lat_deg: float, zoom: int) -> int:
#     lat_rad = math.radians(lat_deg)
#     n = 2**zoom
#     return int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)


# def _tiles_for_bbox(
#     west: float,
#     south: float,
#     east: float,
#     north: float,
#     zoom: int,
# ) -> List[Tuple[int, int]]:
#     """Return all (x, y) tile coordinates that cover the given bounding box."""
#     x_min = _lon_to_tile_x(west, zoom)
#     x_max = _lon_to_tile_x(east, zoom)
#     y_min = _lat_to_tile_y(north, zoom)  # note: y axis is flipped
#     y_max = _lat_to_tile_y(south, zoom)

#     tiles = [
#         (x, y)
#         for x in range(x_min, x_max + 1)
#         for y in range(y_min, y_max + 1)
#     ]
#     return tiles


# # Argentina bounding box (generous, covers all ~15 radars)
# ARGENTINA_BBOX = dict(west=-74.0, south=-55.0, east=-53.0, north=-22.0)


# # ---------------------------------------------------------------------------
# # Data classes
# # ---------------------------------------------------------------------------

# @dataclass
# class RequestResult:
#     url: str
#     status: int
#     elapsed_ms: float
#     error: str | None = None


# @dataclass
# class RunStats:
#     label: str
#     concurrency: int
#     total_requests: int
#     wall_time_s: float
#     results: List[RequestResult] = field(default_factory=list)

#     # Computed after collection
#     ok_count: int = 0
#     error_count: int = 0
#     latencies_ms: List[float] = field(default_factory=list)

#     def compute(self) -> None:
#         self.ok_count = sum(1 for r in self.results if r.error is None and r.status == 200)
#         self.error_count = len(self.results) - self.ok_count
#         self.latencies_ms = [r.elapsed_ms for r in self.results if r.error is None]

#     @property
#     def requests_per_second(self) -> float:
#         return self.total_requests / self.wall_time_s if self.wall_time_s > 0 else 0.0

#     @property
#     def p50(self) -> float:
#         return statistics.median(self.latencies_ms) if self.latencies_ms else 0.0

#     @property
#     def p95(self) -> float:
#         if not self.latencies_ms:
#             return 0.0
#         sorted_lat = sorted(self.latencies_ms)
#         idx = max(0, int(len(sorted_lat) * 0.95) - 1)
#         return sorted_lat[idx]

#     @property
#     def mean(self) -> float:
#         return statistics.mean(self.latencies_ms) if self.latencies_ms else 0.0

#     @property
#     def min_lat(self) -> float:
#         return min(self.latencies_ms) if self.latencies_ms else 0.0

#     @property
#     def max_lat(self) -> float:
#         return max(self.latencies_ms) if self.latencies_ms else 0.0


# # ---------------------------------------------------------------------------
# # Core async benchmark logic
# # ---------------------------------------------------------------------------

# async def _fetch(
#     session: aiohttp.ClientSession,
#     url: str,
#     semaphore: asyncio.Semaphore,
# ) -> RequestResult:
#     """Fetch a single tile URL, respecting the semaphore concurrency limit."""
#     async with semaphore:
#         start = time.perf_counter()
#         try:
#             async with session.get(url) as resp:
#                 await resp.read()  # consume body so connection is returned
#                 elapsed_ms = (time.perf_counter() - start) * 1000
#                 return RequestResult(url=url, status=resp.status, elapsed_ms=elapsed_ms)
#         except Exception as exc:
#             elapsed_ms = (time.perf_counter() - start) * 1000
#             return RequestResult(url=url, status=0, elapsed_ms=elapsed_ms, error=str(exc))


# async def run_benchmark(
#     urls: List[str],
#     concurrency: int,
#     label: str,
#     timeout_s: float = 30.0,
# ) -> RunStats:
#     """Run a full benchmark pass and return a RunStats object."""
#     semaphore = asyncio.Semaphore(concurrency)
#     connector = aiohttp.TCPConnector(limit=concurrency + 4)
#     timeout = aiohttp.ClientTimeout(total=timeout_s)

#     print(f"\n  Running pass: {label}  (concurrency={concurrency}, {len(urls)} requests)")

#     results: List[RequestResult] = []
#     wall_start = time.perf_counter()

#     async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
#         tasks = [_fetch(session, url, semaphore) for url in urls]

#         # Progress dots — one dot per 10% of requests
#         chunk_size = max(1, len(tasks) // 10)
#         completed = 0
#         print("  Progress: [", end="", flush=True)
#         for chunk in _chunked(tasks, chunk_size):
#             chunk_results = await asyncio.gather(*chunk)
#             results.extend(chunk_results)
#             completed += len(chunk_results)
#             print("█", end="", flush=True)
#         print(f"]  {completed}/{len(tasks)} done")

#     wall_time_s = time.perf_counter() - wall_start

#     stats = RunStats(
#         label=label,
#         concurrency=concurrency,
#         total_requests=len(urls),
#         wall_time_s=wall_time_s,
#         results=results,
#     )
#     stats.compute()
#     return stats


# def _chunked(lst, n):
#     """Yield successive n-sized chunks from lst."""
#     for i in range(0, len(lst), n):
#         yield lst[i : i + n]


# # ---------------------------------------------------------------------------
# # URL generation
# # ---------------------------------------------------------------------------

# def build_urls(base_url: str, cog_ids: List[int], zoom: int) -> List[str]:
#     """
#     Build a list of tile URLs for all cog_ids × all tiles covering Argentina
#     at the requested zoom level.
#     """
#     tiles = _tiles_for_bbox(**ARGENTINA_BBOX, zoom=zoom)
#     if not tiles:
#         print(
#             f"WARNING: No tiles found for Argentina bbox at zoom={zoom}. "
#             "Try a lower zoom level.",
#             file=sys.stderr,
#         )
#         sys.exit(1)

#     urls = [
#         f"{base_url}/api/v1/tiles/{cog_id}/{zoom}/{x}/{y}.png"
#         for cog_id, (x, y) in itertools.product(cog_ids, tiles)
#     ]
#     return urls


# # ---------------------------------------------------------------------------
# # Reporting
# # ---------------------------------------------------------------------------

# def _fmt(value: float, unit: str = "ms", width: int = 8) -> str:
#     return f"{value:>{width}.1f} {unit}"


# def print_run_stats(stats: RunStats) -> None:
#     print(f"\n  ┌─ {stats.label} (c={stats.concurrency})")
#     print(f"  │  Total requests : {stats.total_requests}")
#     print(f"  │  HTTP 200 OK    : {stats.ok_count}")
#     print(f"  │  Errors         : {stats.error_count}")
#     print(f"  │  Wall time      : {stats.wall_time_s:.2f} s")
#     print(f"  │  Throughput     : {stats.requests_per_second:.1f} req/s")
#     print(f"  │  Latency min    : {_fmt(stats.min_lat)}")
#     print(f"  │  Latency p50    : {_fmt(stats.p50)}")
#     print(f"  │  Latency mean   : {_fmt(stats.mean)}")
#     print(f"  │  Latency p95    : {_fmt(stats.p95)}")
#     print(f"  └─ Latency max    : {_fmt(stats.max_lat)}")


# def print_comparison(baseline: RunStats, parallel: RunStats) -> None:
#     print("\n" + "=" * 60)
#     print("  COMPARISON SUMMARY")
#     print("=" * 60)

#     header = f"  {'Metric':<28} {'Baseline (c=1)':>16} {'Parallel (c=N)':>16} {'Ratio':>10}"
#     print(header)
#     print("  " + "-" * 72)

#     def row(label: str, b_val: float, p_val: float, unit: str = "ms", lower_is_better: bool = True) -> None:
#         if b_val == 0:
#             ratio_str = "  N/A"
#         else:
#             ratio = p_val / b_val
#             if lower_is_better:
#                 # For latency: ratio < 1 is good (faster)
#                 marker = "✓" if ratio <= 1.0 else "✗"
#             else:
#                 # For throughput: ratio > 1 is good (higher)
#                 marker = "✓" if ratio >= 1.0 else "✗"
#             ratio_str = f"{ratio:>8.2f}x {marker}"
#         print(f"  {label:<28} {b_val:>12.1f} {unit}  {p_val:>12.1f} {unit}  {ratio_str}")

#     row("Wall time",          baseline.wall_time_s,         parallel.wall_time_s,         unit="s ",  lower_is_better=True)
#     row("Throughput",         baseline.requests_per_second,  parallel.requests_per_second, unit="r/s", lower_is_better=False)
#     row("Latency p50",        baseline.p50,                  parallel.p50,                 unit="ms",  lower_is_better=True)
#     row("Latency mean",       baseline.mean,                 parallel.mean,                unit="ms",  lower_is_better=True)
#     row("Latency p95",        baseline.p95,                  parallel.p95,                 unit="ms",  lower_is_better=True)
#     row("Latency max",        baseline.max_lat,              parallel.max_lat,             unit="ms",  lower_is_better=True)

#     print("  " + "-" * 72)
#     ok_b = baseline.ok_count
#     ok_p = parallel.ok_count
#     err_b = baseline.error_count
#     err_p = parallel.error_count
#     print(f"  {'HTTP 200 OK':<28} {ok_b:>13}     {ok_p:>13}")
#     print(f"  {'Errors':<28} {err_b:>13}     {err_p:>13}")
#     print("=" * 60)

#     # Headline
#     if baseline.wall_time_s > 0 and parallel.wall_time_s > 0:
#         speedup = baseline.wall_time_s / parallel.wall_time_s
#         print(f"\n  ★  Overall wall-time speedup: {speedup:.2f}x")
#         if parallel.error_count > 0:
#             error_rate = parallel.error_count / parallel.total_requests * 100
#             print(f"  ⚠  Error rate at c={parallel.concurrency}: {error_rate:.1f}%")

#     print()


# # ---------------------------------------------------------------------------
# # CLI
# # ---------------------------------------------------------------------------

# def parse_args() -> argparse.Namespace:
#     parser = argparse.ArgumentParser(
#         description="Benchmark the WebMet25 /api/v1/tiles/ endpoint.",
#         formatter_class=argparse.RawDescriptionHelpFormatter,
#         epilog=__doc__,
#     )
#     parser.add_argument(
#         "--host",
#         default="localhost",
#         help="Host to benchmark against (default: localhost)",
#     )
#     parser.add_argument(
#         "--port",
#         type=int,
#         default=8080,
#         help="Port (default: 8080, i.e. Caddy entry point)",
#     )
#     parser.add_argument(
#         "--cog-ids",
#         nargs="+",
#         type=int,
#         required=True,
#         metavar="ID",
#         help="One or more RadarCOG IDs to include in the benchmark",
#     )
#     parser.add_argument(
#         "--concurrency",
#         type=int,
#         default=20,
#         help="Max concurrent requests for the parallel pass (default: 20)",
#     )
#     parser.add_argument(
#         "--zoom",
#         type=int,
#         default=7,
#         help="Tile zoom level (default: 7 — ~12 tiles cover Argentina)",
#     )
#     parser.add_argument(
#         "--timeout",
#         type=float,
#         default=30.0,
#         help="Per-request timeout in seconds (default: 30)",
#     )
#     parser.add_argument(
#         "--scheme",
#         choices=["http", "https"],
#         default="http",
#         help="URL scheme (default: http)",
#     )
#     return parser.parse_args()


# # ---------------------------------------------------------------------------
# # Entry point
# # ---------------------------------------------------------------------------

# def main() -> None:
#     args = parse_args()

#     base_url = f"{args.scheme}://{args.host}:{args.port}"
#     urls = build_urls(base_url, args.cog_ids, args.zoom)

#     print("=" * 60)
#     print("  WebMet25 Tile Benchmark")
#     print("=" * 60)
#     print(f"  Target         : {base_url}")
#     print(f"  COG IDs        : {args.cog_ids}")
#     print(f"  Zoom level     : {args.zoom}")
#     print(f"  Tiles/COG      : {len(_tiles_for_bbox(**ARGENTINA_BBOX, zoom=args.zoom))}")
#     print(f"  Total URLs     : {len(urls)}")
#     print(f"  Baseline pass  : concurrency=1")
#     print(f"  Parallel pass  : concurrency={args.concurrency}")

#     # Pass 1 — baseline (sequential, also warms Redis L2)
#     baseline = asyncio.run(
#         run_benchmark(
#             urls,
#             concurrency=1,
#             label="Baseline (sequential)",
#             timeout_s=args.timeout,
#         )
#     )
#     print_run_stats(baseline)

#     # Pass 2 — parallel
#     parallel = asyncio.run(
#         run_benchmark(
#             urls,
#             concurrency=args.concurrency,
#             label=f"Parallel (c={args.concurrency})",
#             timeout_s=args.timeout,
#         )
#     )
#     print_run_stats(parallel)

#     # Comparison table
#     print_comparison(baseline, parallel)


# if __name__ == "__main__":
#     main()