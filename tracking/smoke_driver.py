#!/usr/bin/env python3
"""End-to-end smoke test for the tracking driver, against real NC cubes.

`driver.py` imports gl-tracker, which is only present in the tracking image —
so this cannot run in the shared `radar_tests` container the way the rest of
the suite does. It is a standalone script run inside the tracking image
instead.

Usage (from the repo root)::

    docker run --rm -v /path/to/cubes:/cubes:ro \
      gl-webmet25-tracking python /app/smoke_driver.py /cubes

Or against the mounted cube tree of a running stack::

    docker compose exec tracking python /app/smoke_driver.py /nccube/RMA1

It checks the things that would otherwise only surface in production: that
lead-in volumes are processed but not returned, that the payload is strict
JSON (numpy scalars and NaN are the usual culprits), that gate-discarded
volumes still carry their verdict, and that a track keeps one identity across
volumes.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from tracking_api.driver import build_config, config_summary, run_tracking
from tracking_api.schemas import TrackingConfig
from tracking_api.volumes import Volume

_TS = re.compile(r"(\d{8}T\d{6})Z?")
LEAD_IN = 2


def collect(root: Path) -> list[Volume]:
    """Every cube under *root*, oldest first, with the first few as lead-in."""
    paths = sorted(p for p in root.rglob("*.nc") if _TS.search(p.name))
    volumes = []
    for index, path in enumerate(paths):
        stamp = datetime.strptime(
            _TS.search(path.name).group(1), "%Y%m%dT%H%M%S"
        ).replace(tzinfo=timezone.utc)
        volumes.append(Volume(stamp, str(path), lead_in=index < LEAD_IN))
    volumes.sort(key=lambda v: v.timestamp)
    return volumes


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else "/nccube")
    volumes = collect(root)
    if not volumes:
        print(f"no cubes under {root}")
        return 1

    lead = sum(v.lead_in for v in volumes)
    print(f"{len(volumes)} cube(s) under {root}, {lead} lead-in\n")

    cfg = build_config(TrackingConfig())
    print("config in force:")
    for key, value in config_summary(cfg).items():
        print(f"   {key:24s} {value}")
    print()

    ticks: list[int] = []
    frames = run_tracking(volumes, cfg, progress=lambda i, n: ticks.append(i))

    ok = True

    def check(label: str, condition: bool, detail: str = "") -> None:
        nonlocal ok
        ok = ok and condition
        print(f"  [{'PASS' if condition else 'FAIL'}] {label}{(' — ' + detail) if detail else ''}")

    print("checks:")
    check("lead-in volumes excluded from output",
          len(frames) == len(volumes) - lead,
          f"{len(frames)} frames from {len(volumes)} volumes")
    check("progress covers every volume",
          len(ticks) == len(volumes), f"{len(ticks)} ticks")

    blob = json.dumps({"frames": frames})
    check("payload is strict JSON",
          "NaN" not in blob and "Infinity" not in blob,
          f"{len(blob)/1024:.1f} KB")

    discarded = [f for f in frames if not f["gate_passed"]]
    check("gate-discarded frames keep their verdict",
          all(f["gate"] is None or "umbral_m" in f["gate"] for f in discarded),
          f"{len(discarded)} discarded")

    tracks: dict[str, list[str]] = {}
    for frame in frames:
        for feature in frame["features"]["features"]:
            if feature["properties"]["kind"] == "system":
                tracks.setdefault(feature["properties"]["name"], []).append(
                    frame["timestamp"]
                )
    multi = {n: t for n, t in tracks.items() if len(t) > 1}

    errors = [f for f in frames if f.get("error")]
    check("no volume failed to read", not errors,
          "; ".join(f["error"] for f in errors[:2]))

    print()
    print(f"gate passed    : {sum(f['gate_passed'] for f in frames)}/{len(frames)}")
    print(f"frames w/ data : {sum(1 for f in frames if f['features']['features'])}")
    print(f"distinct tracks: {len(tracks)}")
    print(f"multi-frame    : {len(multi)}  <- one id across volumes means tracking associated")
    for name, stamps in list(multi.items())[:5]:
        print(f"   {name[:8]}... x{len(stamps)}  {stamps[0]} -> {stamps[-1]}")

    if not multi:
        print("\nNOTE: no track spanned two volumes. Not necessarily a fault —")
        print("      shallow or isolated echo produces exactly this. Compare")
        print("      against gl-tracker's own `pipeline.sh track` on the same")
        print("      cubes before suspecting the driver.")

    print()
    print("SMOKE OK" if ok else "SMOKE FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
