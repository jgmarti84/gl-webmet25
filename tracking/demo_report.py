#!/usr/bin/env python3
"""Readable demo of the tracking API — for showing people, not for machines.

Submits a real tracking run and narrates it: what data exists, what the
filtering threw away and why, which storms were followed, and where they are
forecast to go. Everything printed is read back from the service, so nothing
here is staged.

Usage::

    python demo_report.py --radar RMA7 --from 2026-10-20T19:25 --to 2026-10-20T21:15
    python demo_report.py --radar RMA7 --last 3        # last N hours of data

    # against a deployment behind basic auth
    python demo_report.py --base https://host/ --user observatorio --password ... --radar RMA7 --last 3

Runs anywhere with Python 3 — no dependencies beyond the standard library, so
it can be run from a laptop during a demo rather than inside a container.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone

BAR = "─" * 72


# --------------------------------------------------------------------- http

class Client:
    def __init__(self, base: str, user: str | None, password: str | None):
        self.base = base.rstrip("/")
        self.headers = {"Content-Type": "application/json"}
        if user:
            token = base64.b64encode(f"{user}:{password or ''}".encode()).decode()
            self.headers["Authorization"] = f"Basic {token}"

    def _call(self, path: str, payload=None):
        url = f"{self.base}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, headers=self.headers,
                                     method="POST" if data else "GET")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")[:200]
            raise SystemExit(f"\n  {url}\n  HTTP {exc.code}: {body}\n")
        except urllib.error.URLError as exc:
            raise SystemExit(f"\n  Cannot reach {url}: {exc.reason}\n")

    def availability(self):
        return self._call("/api/tracking/availability")["radars"]

    def submit(self, radar, start, end, config=None):
        body = {"radar": radar, "start": start, "end": end}
        if config:
            body["config"] = config
        return self._call("/api/tracking/jobs", body)

    def poll(self, job_id):
        return self._call(f"/api/tracking/jobs/{job_id}")


# ------------------------------------------------------------------ helpers

def hhmm(iso: str) -> str:
    return str(iso)[11:16]


def fmt(v, digits=0, dash="—"):
    if v is None:
        return dash
    return f"{v:.{digits}f}"


def pick(props, *keys):
    for key in keys:
        if props.get(key) is not None:
            return props[key]
    return None


def compass(deg):
    if deg is None:
        return ""
    points = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
    return points[round(deg / 45) % 8]


# ------------------------------------------------------------------ report

def report(radar, window, result):
    frames = result.get("frames") or []
    cfg = result.get("config_in_force") or {}

    print(BAR)
    print(f"  SEGUIMIENTO DE TORMENTAS — {radar}")
    print(f"  Ventana analizada: {window}")
    print(BAR)

    # -- 1. what was actually processed ------------------------------------
    passed = [f for f in frames if f.get("gate_passed")]
    discarded = [f for f in frames if not f.get("gate_passed")]

    print("\n1. VOLÚMENES PROCESADOS\n")
    print(f"   Volúmenes de radar analizados : {len(frames)}")
    print(f"   Con convección significativa  : {len(passed)}")
    print(f"   Descartados por el filtro     : {len(discarded)}")

    if discarded:
        sample = discarded[0].get("gate") or {}
        if sample.get("umbral_m") is not None:
            print(f"\n   El filtro no descarta por falta de eco, sino por profundidad:")
            print(f"   exige que el tope de eco supere los {fmt(sample.get('umbral_m'))} m")
            print(f"   (isoterma 0°C a {fmt(sample.get('h0_msnm'))} m + "
                  f"{fmt(cfg.get('echotop_min_above_h0_m'))} m).")
            tops = [f["gate"].get("tope_max_m") for f in discarded
                    if f.get("gate") and f["gate"].get("tope_max_m") is not None]
            if tops:
                print(f"   En los descartados el tope llegó como máximo a {fmt(max(tops))} m.")

    # -- 2. the storms -----------------------------------------------------
    tracks = defaultdict(list)
    for frame in frames:
        for feat in (frame.get("features") or {}).get("features", []):
            props = feat.get("properties") or {}
            if props.get("kind") == "system":
                tracks[props["name"]].append((frame["timestamp"], props))

    followed = {k: v for k, v in tracks.items() if len(v) > 1}

    print("\n2. SISTEMAS DETECTADOS Y SEGUIDOS\n")
    print(f"   Sistemas convectivos detectados : {len(tracks)}")
    print(f"   Seguidos en el tiempo (≥2 vol.) : {len(followed)}")

    if followed:
        print(f"\n   {'Tormenta':<10} {'Desde':<7} {'Hasta':<7} {'Dur.':<7} "
              f"{'Vol.':<5} {'Máx dBZ':<9} {'Tope':<8} {'Desplazamiento'}")
        print(f"   {'-' * 10} {'-' * 7} {'-' * 7} {'-' * 7} {'-' * 5} "
              f"{'-' * 9} {'-' * 8} {'-' * 20}")

        for name, entries in sorted(followed.items(), key=lambda kv: -len(kv[1])):
            stamps = [e[0] for e in entries]
            props = [e[1] for e in entries]
            t0 = datetime.fromisoformat(stamps[0].replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(stamps[-1].replace("Z", "+00:00"))
            minutes = int((t1 - t0).total_seconds() / 60)

            dbz = max((pick(p, "core_max_dbz", "max") or 0) for p in props)
            top = max((p.get("echo_top_max_m") or 0) for p in props)
            speed = next((p.get("velocity") for p in reversed(props)
                          if p.get("velocity")), None)
            head = next((p.get("direction") for p in reversed(props)
                         if p.get("direction") is not None), None)
            motion = (f"{speed * 3.6:.0f} km/h hacia {compass(head)}"
                      if speed else "—")

            print(f"   {name[:8]:<10} {hhmm(stamps[0]):<7} {hhmm(stamps[-1]):<7} "
                  f"{str(minutes) + ' min':<7} {len(entries):<5} "
                  f"{fmt(dbz, 1):<9} {fmt(top) + ' m':<8} {motion}")

    # -- 3. forecasts ------------------------------------------------------
    leads = sorted({
        f["properties"]["lead_min"]
        for frame in frames
        for f in (frame.get("features") or {}).get("features", [])
        if f.get("properties", {}).get("kind") == "forecast"
    })
    n_forecast = sum(f.get("counts", {}).get("forecasts", 0) for f in frames)

    print("\n3. PRONÓSTICO DE TRAYECTORIA\n")
    if leads:
        print(f"   Polígonos de pronóstico generados : {n_forecast}")
        print(f"   Horizontes (minutos)              : {', '.join(map(str, leads))}")
        print(f"\n   Para cada tormenta seguida se proyecta su posición hasta")
        print(f"   {max(leads)} minutos hacia adelante, a partir de su desplazamiento real.")
    else:
        print("   Ninguno: se generan sólo para tormentas vistas en 2+ volúmenes")
        print("   consecutivos, que es lo que permite medir su desplazamiento.")

    # -- 4. configuration --------------------------------------------------
    print("\n4. CONFIGURACIÓN UTILIZADA\n")
    shown = [
        ("Altura del CAPPI de detección", "cappi_height_m", " m sobre antena"),
        ("Umbral de reflectividad", "dbz_threshold", " dBZ"),
        ("Área mínima del sistema", "min_area_km2", " km²"),
        ("Tope mínimo sobre isoterma 0°C", "echotop_min_above_h0_m", " m"),
        ("Solape mínimo para asociar", "overlap", ""),
    ]
    for label, key, unit in shown:
        if cfg.get(key) is not None:
            print(f"   {label:<34} {cfg[key]}{unit}")
    print("\n   Todos estos valores son ajustables por llamada a la API.")
    print(BAR)


# -------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://localhost:8001")
    ap.add_argument("--user")
    ap.add_argument("--password")
    ap.add_argument("--radar")
    ap.add_argument("--from", dest="start", help="UTC, e.g. 2026-10-20T19:25")
    ap.add_argument("--to", dest="end", help="UTC")
    ap.add_argument("--last", type=float, help="instead of --from/--to: last N hours")
    ap.add_argument("--cappi", type=float, help="override CAPPI height, metres")
    args = ap.parse_args()

    client = Client(args.base, args.user, args.password)

    radars = client.availability()
    if not radars:
        print("No hay volúmenes indexados todavía.")
        return 1

    print("\nDATOS DISPONIBLES\n")
    for r in radars:
        print(f"   {r['radar_code']:<7} {r['count']:>5} volúmenes   "
              f"{str(r['min_time'])[:16].replace('T', ' ')} → "
              f"{str(r['max_time'])[:16].replace('T', ' ')} UTC")

    radar = (args.radar or radars[0]["radar_code"]).upper()
    chosen = next((r for r in radars if r["radar_code"] == radar), None)
    if chosen is None:
        print(f"\n{radar} no tiene volúmenes indexados.")
        return 1

    if args.last:
        end_dt = datetime.fromisoformat(chosen["max_time"].replace("Z", "+00:00"))
        start_dt = end_dt - timedelta(hours=args.last)
        start, end = start_dt.isoformat().replace("+00:00", "Z"), chosen["max_time"]
    else:
        if not (args.start and args.end):
            print("\nIndicá --from/--to o --last N")
            return 1
        start = args.start if args.start.endswith("Z") else args.start + ":00Z"
        end = args.end if args.end.endswith("Z") else args.end + ":00Z"

    config = {"cappi_height_m": args.cappi} if args.cappi else None
    window = f"{start[:16].replace('T', ' ')} → {end[:16].replace('T', ' ')} UTC"

    print(f"\nAnalizando {radar}: {window}")
    job = client.submit(radar, start, end, config)
    if job.get("cached"):
        print("   (resultado ya en caché — respuesta inmediata)")

    t0 = time.time()
    while True:
        state = client.poll(job["job_id"])
        if state["status"] == "done":
            break
        if state["status"] == "error":
            print(f"   Error: {state.get('error')}")
            return 1
        prog = state.get("progress") or {}
        if prog.get("volumes_total"):
            pct = int(100 * prog["volumes_done"] / prog["volumes_total"])
            print(f"\r   procesando… {prog['volumes_done']}/{prog['volumes_total']} "
                  f"volúmenes ({pct}%)", end="", flush=True)
        time.sleep(1)

    print(f"\r   completado en {time.time() - t0:.0f} s" + " " * 30 + "\n")
    report(radar, window, state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
