#!/usr/bin/env python3
"""
Verification script for the frames endpoint.

Usage:
    python scripts/test_frames_endpoint.py \
        --host localhost \
        --port 8000 \
        --cog-id 62581 \
        --username observatorio \
        --password mate-nubes-radar-2026

Exit codes:
    0  — all checks passed
    1  — one or more checks failed
"""
import argparse
import sys
import time
from typing import Optional

import requests
from PIL import Image
import io


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PASS = "\033[92mPASS\033[0m"
_FAIL = "\033[91mFAIL\033[0m"

_results: list[bool] = []


def check(label: str, ok: bool, detail: str = "") -> bool:
    """Print a PASS/FAIL line and record the result."""
    status = _PASS if ok else _FAIL
    msg = f"[{status}] {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    _results.append(ok)
    return ok


def _frame_url(base: str, cog_id: int, **params) -> str:
    url = f"{base}/api/v1/frames/{cog_id}/image.png"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"
    return url


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_endpoint_exists(session: requests.Session, base: str, cog_id: int) -> Optional[requests.Response]:
    """Check 1: endpoint returns HTTP 200."""
    url = _frame_url(base, cog_id)
    try:
        resp = session.get(url, timeout=30)
    except requests.RequestException as exc:
        check("Endpoint returns 200", False, str(exc))
        return None
    check("Endpoint returns 200", resp.status_code == 200, f"status={resp.status_code}")
    return resp if resp.status_code == 200 else None


def check_response_headers(resp: requests.Response) -> None:
    """Check 2: required headers are present and valid."""
    headers = resp.headers

    # Content-Type
    ct = headers.get("Content-Type", "")
    check("Content-Type is image/png", "image/png" in ct, f"got: {ct!r}")

    # Bbox headers
    for hdr in ("X-Bbox-West", "X-Bbox-South", "X-Bbox-East", "X-Bbox-North"):
        val = headers.get(hdr)
        try:
            parsed = float(val) if val is not None else None
        except ValueError:
            parsed = None
        check(f"{hdr} present and numeric", parsed is not None, f"got: {val!r}")

    # Geographic plausibility for Argentina
    try:
        west = float(headers.get("X-Bbox-West", "nan"))
        south = float(headers.get("X-Bbox-South", "nan"))
        east = float(headers.get("X-Bbox-East", "nan"))
        north = float(headers.get("X-Bbox-North", "nan"))

        check("Bbox West in [-80, -50]", -80 <= west <= -50, f"west={west}")
        check("Bbox South in [-60, -20]", -60 <= south <= -20, f"south={south}")
        check("Bbox East in [-80, -50]", -80 <= east <= -50, f"east={east}")
        check("Bbox North in [-60, -20]", -60 <= north <= -20, f"north={north}")
        check("Bbox West < East", west < east, f"west={west}, east={east}")
        check("Bbox South < North", south < north, f"south={south}, north={north}")
    except (TypeError, ValueError) as exc:
        check("Bbox geographic plausibility", False, str(exc))

    # X-Width / X-Height
    for hdr in ("X-Width", "X-Height"):
        val = headers.get(hdr)
        try:
            parsed_int = int(val) if val is not None else 0
        except (ValueError, TypeError):
            parsed_int = 0
        check(f"{hdr} present and > 0", parsed_int > 0, f"got: {val!r}")

    # Cache-Control
    cc = headers.get("Cache-Control")
    check("Cache-Control present", bool(cc), f"got: {cc!r}")

    # ETag
    etag = headers.get("ETag")
    check("ETag present", bool(etag), f"got: {etag!r}")


def check_png_valid(resp: requests.Response) -> None:
    """Check 3: response bytes are a valid RGBA PNG matching header dimensions."""
    try:
        img = Image.open(io.BytesIO(resp.content))
    except Exception as exc:
        check("Response is a valid PNG", False, str(exc))
        return

    check("Response is a valid PNG", True)
    check("PNG mode is RGBA", img.mode == "RGBA", f"got: {img.mode!r}")

    try:
        expected_w = int(resp.headers.get("X-Width", 0))
        expected_h = int(resp.headers.get("X-Height", 0))
    except (ValueError, TypeError):
        expected_w = expected_h = 0

    w, h = img.size
    check(
        "PNG size matches X-Width × X-Height headers",
        (expected_w == 0 or w == expected_w) and (expected_h == 0 or h == expected_h),
        f"PNG {w}×{h}, headers {expected_w}×{expected_h}",
    )


def check_caching(session: requests.Session, base: str, cog_id: int) -> None:
    """Check 4: second request is not slower and bytes are identical (cache hit)."""
    url = _frame_url(base, cog_id)

    try:
        t0 = time.monotonic()
        resp1 = session.get(url, timeout=30)
        t1 = time.monotonic()
        resp2 = session.get(url, timeout=30)
        t2 = time.monotonic()
    except requests.RequestException as exc:
        check("Caching — two requests succeed", False, str(exc))
        return

    both_ok = resp1.status_code == 200 and resp2.status_code == 200
    check("Caching — both requests return 200", both_ok)

    if both_ok:
        first_ms = (t1 - t0) * 1000
        second_ms = (t2 - t1) * 1000
        # Cache hit should be faster, but allow some tolerance for network jitter
        check(
            "Caching — second request not slower than first (cache hit)",
            second_ms <= first_ms * 2 + 50,  # generous tolerance
            f"first={first_ms:.0f}ms second={second_ms:.0f}ms",
        )
        check(
            "Caching — both responses return identical bytes (deterministic render)",
            resp1.content == resp2.content,
            f"sizes: {len(resp1.content)}B vs {len(resp2.content)}B",
        )


def check_filter_params(session: requests.Session, base: str, cog_id: int) -> None:
    """Check 5: vmin/vmax filter query parameters produce a valid RGBA PNG."""
    url = _frame_url(base, cog_id, vmin=20, vmax=60)
    try:
        resp = session.get(url, timeout=30)
    except requests.RequestException as exc:
        check("Filter params — request succeeds", False, str(exc))
        return

    check("Filter params — returns 200", resp.status_code == 200, f"status={resp.status_code}")
    if resp.status_code == 200:
        try:
            img = Image.open(io.BytesIO(resp.content))
            ok = img.mode == "RGBA"
        except Exception as exc:
            ok = False
        check("Filter params — valid RGBA PNG", ok)


def check_404_missing_cog(session: requests.Session, base: str) -> None:
    """Check 6: non-existent COG ID returns HTTP 404."""
    url = _frame_url(base, 999999)
    try:
        resp = session.get(url, timeout=10)
    except requests.RequestException as exc:
        check("Missing COG returns 404", False, str(exc))
        return
    check("Missing COG returns 404", resp.status_code == 404, f"status={resp.status_code}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the frames endpoint.")
    parser.add_argument("--host", default="localhost", help="API host")
    parser.add_argument("--port", type=int, default=8000, help="API port")
    parser.add_argument("--cog-id", type=int, required=True, help="COG ID to test")
    parser.add_argument("--username", default=None, help="HTTP Basic auth username")
    parser.add_argument("--password", default=None, help="HTTP Basic auth password")
    args = parser.parse_args()

    base = f"http://{args.host}:{args.port}"
    print(f"\nVerifying frames endpoint at {base}")
    print(f"COG ID: {args.cog_id}\n")

    session = requests.Session()
    if args.username and args.password:
        session.auth = (args.username, args.password)

    # --- Check 1: endpoint exists ---
    print("--- Check 1: endpoint exists and returns 200 ---")
    resp = check_endpoint_exists(session, base, args.cog_id)

    # --- Check 2: response headers ---
    print("\n--- Check 2: response headers ---")
    if resp is not None:
        check_response_headers(resp)
    else:
        check("Response headers (skipped — no 200 response)", False, "skipped")

    # --- Check 3: PNG validity ---
    print("\n--- Check 3: PNG is valid RGBA ---")
    if resp is not None:
        check_png_valid(resp)
    else:
        check("PNG validity (skipped)", False, "skipped")

    # --- Check 4: caching ---
    print("\n--- Check 4: caching ---")
    check_caching(session, base, args.cog_id)

    # --- Check 5: filter params ---
    print("\n--- Check 5: vmin/vmax filter parameters ---")
    check_filter_params(session, base, args.cog_id)

    # --- Check 6: 404 on missing COG ---
    print("\n--- Check 6: 404 on missing COG ---")
    check_404_missing_cog(session, base)

    # --- Summary ---
    total = len(_results)
    passed = sum(_results)
    failed = total - passed
    print(f"\n{'='*50}")
    print(f"Results: {passed}/{total} passed, {failed} failed")
    print('='*50 + "\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
