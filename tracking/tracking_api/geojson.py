"""Turn gl-tracker's ConvectiveSystem objects into GeoJSON.

``scripts/export_map.py`` in gl-tracker does the equivalent against SpatiaLite
rows; this does it against the live objects, which is both faster and avoids
writing a database nobody reads.

Three properties carry the tracking semantics and must survive verbatim:

``name``
    The track identifier. ``ConvectiveSystem.__init__`` assigns a UUID, and on
    a successful match the current system **inherits the previous system's
    name** (``tathu/tracking/trackers.py:213``). Systems sharing a ``name``
    across volumes are one storm. Lose this and the output is per-frame
    detection, not tracking.

``event``
    ``SPONTANEOUS_GENERATION`` / ``NATURAL_DISSIPATION`` / ``CONTINUITY`` /
    ``SPLIT`` / ``MERGE`` / ``INTERPOLATION``.

``relationships``
    The parent systems' names. Splits and merges are unreconstructable without
    both this and ``event``.
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

#: Attached by StatisticalDescriptor(rasterOut=True) — a per-system crop of the
#: reflectivity raster. Useful for debugging in a notebook, useless over HTTP,
#: and large. Dropped.
_SKIP_ATTRS = {"raster", "nodata", "geotransform"}


def _json_safe(value: Any) -> Any:
    """Coerce numpy scalars, NaN and Inf into something ``json`` accepts.

    gl-tracker's attributes come from numpy reductions, so they are numpy
    scalars rather than Python ones, and a system with no valid pixels yields
    NaN. ``json.dumps`` renders those as bare ``NaN``/``Infinity``, which is
    invalid JSON that many clients reject.
    """
    if value is None:
        return None
    if isinstance(value, (bool, str, int)):
        return value
    # numpy scalars expose .item(); do this before the float check so that
    # np.float32 becomes a Python float rather than staying numpy.
    item = getattr(value, "item", None)
    if callable(item) and not isinstance(value, (list, tuple, dict)):
        try:
            value = value.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (bool, str, int)):
        return value
    return str(value)


def _attrs(system) -> Dict[str, Any]:
    return {
        key: _json_safe(val)
        for key, val in (system.attrs or {}).items()
        if key not in _SKIP_ATTRS
    }


def system_to_feature(
    system,
    kind: str = "system",
    lead_min: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """One ConvectiveSystem as a GeoJSON Feature, or None if it has no geometry."""
    geom = getattr(system, "geom", None)
    if geom is None:
        return None

    try:
        geometry = json.loads(geom.ExportToJson())
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("could not serialise geometry for %s: %s", system.name, exc)
        return None

    props: Dict[str, Any] = {
        "kind": kind,
        "name": str(system.name),
        "event": str(system.event) if system.event is not None else None,
        "relationships": [str(n) for n in system.getRelationshipNames()],
    }
    if system.timestamp is not None:
        props["timestamp"] = system.timestamp.isoformat().replace("+00:00", "Z")
    if lead_min is not None:
        props["lead_min"] = lead_min

    props.update(_attrs(system))

    return {"type": "Feature", "geometry": geometry, "properties": props}


def sink_to_features(sink) -> List[Dict[str, Any]]:
    """Every feature from one volume: tracked systems, then their forecasts.

    Forecast polygons exist only for systems that matched a previous frame —
    there is nothing to extrapolate from otherwise — so an early or isolated
    volume yields systems with no forecasts, which is correct rather than
    missing data.
    """
    features: List[Dict[str, Any]] = []

    for system in sink.systems.rows:
        feature = system_to_feature(system, kind="system")
        if feature is not None:
            features.append(feature)

    for lead in sorted(sink.forecasts):
        for system in sink.forecasts[lead].rows:
            feature = system_to_feature(system, kind="forecast", lead_min=lead)
            if feature is not None:
                features.append(feature)

    return features


def gate_to_dict(resultado_gate) -> Dict[str, Any]:
    """The gate's verdict and the numbers behind it.

    Kept even when the gate passes: with the gate able to discard a whole
    volume, ``tope_max_m`` against ``umbral_m`` is the only thing that later
    explains why a storm never appeared (``gate.py:128-131``).
    """
    return {
        "passed": bool(resultado_gate.pasa),
        "tope_max_m": _json_safe(resultado_gate.tope_max_m),
        "umbral_m": _json_safe(resultado_gate.umbral_m),
        "n_pixeles_pasan": _json_safe(resultado_gate.n_pixeles_pasan),
        "h0_msnm": _json_safe(resultado_gate.h0_msnm),
        "h0_fuente": resultado_gate.h0_fuente,
        "referencia_z": resultado_gate.referencia_z,
    }


def build_frame(timestamp, resultado, sink) -> Dict[str, Any]:
    """One observation time's complete result.

    A volume the gate discarded still produces a frame — with no features but
    with the verdict — so a client can distinguish "filtered out" from "no data
    for this time", which otherwise look identical.
    """
    gate_passed = bool(resultado.gate.pasa)
    features = sink_to_features(sink) if gate_passed else []

    return {
        "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
        "gate_passed": gate_passed,
        "gate": gate_to_dict(resultado.gate),
        "counts": {
            "detected": resultado.detectados,
            "convective": resultado.convectivos,
            "tracked": resultado.rastreados,
            "forecasts": resultado.forecasts,
        },
        "tracking_restarted": bool(resultado.reinicio_tracking),
        "seconds": round(float(resultado.segundos), 3),
        "features": {"type": "FeatureCollection", "features": features},
    }
