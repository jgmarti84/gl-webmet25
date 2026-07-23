#!/usr/bin/env python3
"""
Importa un CSV de colores (valor físico → R,G,B) como mapa de colores en WebMet25
usando la API de administración (endpoint de stops individuales por canal).

La posición normalizada [0, 1] se calcula como:
    pos = (valor - vmin) / (vmax - vmin)

Si --vmin / --vmax no se especifican, se usan el mínimo y máximo del propio CSV.

Discontinuidades: si la distancia euclidiana en RGB entre un stop y el anterior
supera --threshold, el stop se inserta con val_left = color_anterior (corte abrupto).
Con threshold=0 todos los stops son suaves (equivalente a Option A).

Uso:
    python scripts/import_colormap.py \\
        --csv mi_colormap.csv \\
        --name grc_dbzh_custom \\
        --vmin -30 --vmax 75 \\
        --products DBZH DBZHo \\
        --api http://localhost \\
        [--value-col dBZ] [--r-col R] [--g-col G] [--b-col B] \\
        [--threshold 0.3] \\
        [--overwrite]
"""

import argparse
import csv
import math
import sys

try:
    import requests
except ImportError:
    sys.exit("Instala requests:  pip install requests")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Importa colormap CSV → WebMet25 admin API (Option B, stops por canal)"
    )
    p.add_argument("--csv", required=True, metavar="ARCHIVO",
                   help="Ruta al CSV de entrada")
    p.add_argument("--name", required=True, metavar="NOMBRE",
                   help="Nombre del mapa de colores en la base de datos (cmap_name)")

    grp_norm = p.add_argument_group("Normalización")
    grp_norm.add_argument("--vmin", type=float, default=None,
                          help="Valor físico que mapea a posición 0.0 "
                               "(por defecto: mínimo del CSV)")
    grp_norm.add_argument("--vmax", type=float, default=None,
                          help="Valor físico que mapea a posición 1.0 "
                               "(por defecto: máximo del CSV)")

    grp_cols = p.add_argument_group("Columnas del CSV")
    grp_cols.add_argument("--value-col", default="dBZ", metavar="COL",
                          help="Columna del valor físico (default: dBZ)")
    grp_cols.add_argument("--r-col", default="R", metavar="COL",
                          help="Columna rojo 0-255 (default: R)")
    grp_cols.add_argument("--g-col", default="G", metavar="COL",
                          help="Columna verde 0-255 (default: G)")
    grp_cols.add_argument("--b-col", default="B", metavar="COL",
                          help="Columna azul 0-255 (default: B)")

    grp_api = p.add_argument_group("API / comportamiento")
    grp_api.add_argument("--api", default="http://localhost",
                         help="URL base del stack (default: http://localhost)")
    grp_api.add_argument("--products", nargs="*", default=[],
                         metavar="PRODUCTO",
                         help="Claves de producto a asociar (ej. DBZH DBZHo)")
    grp_api.add_argument("--threshold", type=float, default=0.30,
                         metavar="T",
                         help="Distancia RGB [0-√3] para detectar discontinuidades "
                              "(default: 0.30 ; 0 = todos suaves)")
    grp_api.add_argument("--overwrite", action="store_true",
                         help="Eliminar el mapa existente con ese nombre antes de importar")
    grp_api.add_argument("--dry-run", action="store_true",
                         help="Calcular y mostrar los stops sin hacer ninguna llamada a la API")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Lectura del CSV
# ---------------------------------------------------------------------------

def read_csv(path: str, value_col: str, r_col: str, g_col: str, b_col: str) -> list[dict]:
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):
            try:
                rows.append({
                    "value": float(row[value_col]),
                    "r": int(row[r_col]) / 255.0,
                    "g": int(row[g_col]) / 255.0,
                    "b": int(row[b_col]) / 255.0,
                })
            except (KeyError, ValueError) as exc:
                sys.exit(f"Error en CSV fila {i}: {exc}")
    if len(rows) < 2:
        sys.exit("El CSV debe tener al menos 2 filas de datos.")
    return rows


# ---------------------------------------------------------------------------
# Lógica de stops
# ---------------------------------------------------------------------------

def rgb_distance(a: dict, b: dict) -> float:
    return math.sqrt(
        (a["r"] - b["r"]) ** 2 +
        (a["g"] - b["g"]) ** 2 +
        (a["b"] - b["b"]) ** 2
    )


def normalize(value: float, vmin: float, vmax: float) -> float:
    return round((value - vmin) / (vmax - vmin), 8)


def build_stops(rows: list[dict], vmin: float, vmax: float, threshold: float) -> list[dict]:
    """
    Construye la lista de stops en formato LinearSegmentedColormap:
      - val_left / val_right iguales → transición suave (interpolación)
      - val_left = color anterior, val_right = color propio → escalón abrupto

    La lógica de discontinuidad opera en el stop DE LLEGADA:
    cuando el salto desde el stop anterior supera el umbral, val_left toma
    el color del stop anterior, creando el corte sin afectar al stop anterior.
    """
    result = []
    for i, row in enumerate(rows):
        pos = normalize(row["value"], vmin, vmax)

        # Por defecto: suave
        vl = {"r": row["r"], "g": row["g"], "b": row["b"]}
        vr = {"r": row["r"], "g": row["g"], "b": row["b"]}
        is_disc = False

        if i > 0 and threshold > 0:
            dist = rgb_distance(rows[i - 1], row)
            if dist >= threshold:
                # Escalón: val_left = color del stop anterior
                vl = {"r": rows[i - 1]["r"], "g": rows[i - 1]["g"], "b": rows[i - 1]["b"]}
                is_disc = True

        result.append({
            "position": pos,
            "physical": row["value"],
            "vl_r": vl["r"], "vr_r": vr["r"],
            "vl_g": vl["g"], "vr_g": vr["g"],
            "vl_b": vl["b"], "vr_b": vr["b"],
            "is_disc": is_disc,
        })
    return result


# ---------------------------------------------------------------------------
# Llamadas a la API
# ---------------------------------------------------------------------------

def post_channel_stop(
    session: "requests.Session",
    api: str,
    cmap_name: str,
    channel: str,
    position: float,
    val_left: float,
    val_right: float,
) -> None:
    resp = session.post(
        f"{api}/api/v1/admin/colormap-stops",
        json={
            "cmap_name": cmap_name,
            "channel": channel,
            "position": position,
            "val_left": val_left,
            "val_right": val_right,
            "sort_order": 0,
            "is_system": False,
        },
        timeout=10,
    )
    if not resp.ok:
        sys.exit(
            f"\nError al insertar stop {channel}@{position:.6f}: "
            f"{resp.status_code} {resp.text}"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    # --- Leer CSV ----------------------------------------------------------
    rows = read_csv(args.csv, args.value_col, args.r_col, args.g_col, args.b_col)
    values = [r["value"] for r in rows]

    vmin = args.vmin if args.vmin is not None else min(values)
    vmax = args.vmax if args.vmax is not None else max(values)

    if vmin >= vmax:
        sys.exit(f"vmin ({vmin}) debe ser menor que vmax ({vmax}).")

    # Advertir si el CSV tiene valores fuera del rango de normalización
    out_of_range = [v for v in values if v < vmin or v > vmax]
    if out_of_range:
        print(
            f"ADVERTENCIA: {len(out_of_range)} fila(s) tienen valor fuera de "
            f"[{vmin}, {vmax}] y producirán posiciones fuera de [0, 1]:\n"
            f"  {out_of_range}"
        )

    print(f"CSV:          {args.csv}  ({len(rows)} filas)")
    print(f"Rango físico: [{min(values):.2f}, {max(values):.2f}]")
    print(f"Normalizar:   [{vmin:.2f}, {vmax:.2f}] → [0.0, 1.0]")
    print(f"Nombre cmap:  {args.name}")
    print(f"Threshold:    {args.threshold}  (√3 ≈ 1.732)")

    # --- Construir stops ---------------------------------------------------
    stops = build_stops(rows, vmin, vmax, args.threshold)
    disc_stops = [s for s in stops if s["is_disc"]]

    print(f"\nStops totales:       {len(stops)}  (→ {len(stops) * 3} filas en BD)")
    print(f"Discontinuidades:    {len(disc_stops)}")
    if disc_stops:
        for s in disc_stops:
            print(f"  valor={s['physical']:.1f}  pos={s['position']:.6f}")

    # --- Dry-run -----------------------------------------------------------
    if args.dry_run:
        print("\n[dry-run] Primeros 5 stops calculados:")
        for s in stops[:5]:
            print(
                f"  pos={s['position']:.6f}  "
                f"R vl={s['vl_r']:.3f} vr={s['vr_r']:.3f}  "
                f"G vl={s['vl_g']:.3f} vr={s['vr_g']:.3f}  "
                f"B vl={s['vl_b']:.3f} vr={s['vr_b']:.3f}"
                + ("  ← DISC" if s["is_disc"] else "")
            )
        print("\n[dry-run] Sin llamadas a la API.")
        return

    # --- Verificar / eliminar existente ------------------------------------
    api = args.api.rstrip("/")
    session = requests.Session()

    print(f"\nAPI base: {api}")
    existing = session.get(f"{api}/api/v1/admin/colormap-stops/{args.name}", timeout=10)
    if existing.status_code == 200:
        if not args.overwrite:
            sys.exit(
                f"El mapa '{args.name}' ya existe. "
                f"Usá --overwrite para reemplazarlo."
            )
        print(f"Eliminando colormap existente '{args.name}'…")
        del_resp = session.delete(
            f"{api}/api/v1/admin/colormap-stops/{args.name}", timeout=10
        )
        if not del_resp.ok:
            sys.exit(f"No se pudo eliminar: {del_resp.status_code} {del_resp.text}")
        print("  Eliminado.")
    elif existing.status_code not in (404,):
        sys.exit(f"Error al verificar existencia: {existing.status_code} {existing.text}")

    # --- Insertar stops ----------------------------------------------------
    total_rows = len(stops) * 3
    inserted = 0
    print(f"\nInsertando {total_rows} filas en colormap_stops…")

    for stop in stops:
        for ch, vl, vr in (
            ("r", stop["vl_r"], stop["vr_r"]),
            ("g", stop["vl_g"], stop["vr_g"]),
            ("b", stop["vl_b"], stop["vr_b"]),
        ):
            post_channel_stop(session, api, args.name, ch, stop["position"], vl, vr)
            inserted += 1

        if inserted % 30 == 0 or inserted == total_rows:
            pct = inserted / total_rows * 100
            print(f"  {inserted}/{total_rows}  ({pct:.0f}%)")

    # --- Asociar productos -------------------------------------------------
    if args.products:
        print("\nAsociando productos…")
        for pk in args.products:
            resp = session.post(
                f"{api}/api/v1/admin/colormap-options",
                json={"product_key": pk, "cmap_name": args.name},
                timeout=10,
            )
            if resp.status_code == 409:
                print(f"  '{pk}' ya estaba asociado (sin cambios).")
            elif resp.ok:
                print(f"  '{pk}' → vinculado.")
            else:
                print(f"  ADVERTENCIA '{pk}': {resp.status_code} {resp.text}")

    # --- Invalidar caché ---------------------------------------------------
    inv = session.post(f"{api}/api/v1/colormap/cache/invalidate", timeout=10)
    if inv.ok:
        print("\nCaché invalidado.")
    else:
        print(f"\nADVERTENCIA: no se pudo invalidar la caché: {inv.status_code}")

    print(f"\nListo. El mapa '{args.name}' está disponible en el stack.")


if __name__ == "__main__":
    main()
