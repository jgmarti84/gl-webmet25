"""Tests for GeoJSON serialisation.

Two things here are easy to get wrong and fail far from their cause: numpy
scalars and non-finite floats producing invalid JSON, and losing the three
properties that make the output *tracking* rather than per-frame detection.

These use duck-typed stand-ins rather than real ConvectiveSystem objects, so
they run in the ordinary tests image without gl-tracker on the path.
"""

import json
import math

import pytest

from tracking_api.geojson import (
    build_frame,
    gate_to_dict,
    sink_to_features,
    system_to_feature,
)
from tracking_api.sink import VolumeSink

POLY = '{"type":"Polygon","coordinates":[[[0,0],[1,0],[1,1],[0,1],[0,0]]]}'


class FakeGeom:
    def __init__(self, blob=POLY): self._blob = blob
    def ExportToJson(self): return self._blob


class FakeSystem:
    def __init__(self, name="abc", event="CONTINUITY", rels=(), attrs=None,
                 geom=None, timestamp=None):
        self.name = name
        self.event = event
        self.geom = FakeGeom() if geom is None else geom
        self.attrs = attrs or {}
        self.timestamp = timestamp
        self._rels = list(rels)

    def getRelationshipNames(self): return self._rels


class FakeGate:
    pasa = True
    tope_max_m = 4800.0
    umbral_m = 4841.0
    n_pixeles_pasan = 0
    h0_msnm = 3716.0
    h0_fuente = "climatologia"
    referencia_z = "radar"


class FakeResultado:
    def __init__(self, passed=True):
        self.gate = FakeGate()
        self.gate.pasa = passed
        self.detectados = 3
        self.convectivos = 2
        self.rastreados = 1
        self.forecasts = 7
        self.reinicio_tracking = False
        self.segundos = 0.4123


class TestIdentityProperties:
    """name / event / relationships are what make this tracking output."""

    def test_preserves_track_name(self):
        f = system_to_feature(FakeSystem(name="track-1"))
        assert f["properties"]["name"] == "track-1"

    def test_preserves_event(self):
        f = system_to_feature(FakeSystem(event="SPLIT"))
        assert f["properties"]["event"] == "SPLIT"

    def test_preserves_relationships(self):
        f = system_to_feature(FakeSystem(rels=["parent-a", "parent-b"]))
        assert f["properties"]["relationships"] == ["parent-a", "parent-b"]

    def test_name_is_stringified(self):
        """ConvectiveSystem.name is a uuid.UUID, not a str."""
        import uuid
        u = uuid.uuid4()
        f = system_to_feature(FakeSystem(name=u))
        assert f["properties"]["name"] == str(u)


class TestJsonSafety:
    """numpy scalars and non-finite floats must not reach json.dumps."""

    def test_nan_becomes_null(self):
        f = system_to_feature(FakeSystem(attrs={"core_max_dbz": float("nan")}))
        assert f["properties"]["core_max_dbz"] is None

    def test_infinity_becomes_null(self):
        f = system_to_feature(FakeSystem(attrs={"echo_top_max_m": float("inf")}))
        assert f["properties"]["echo_top_max_m"] is None

    def test_finite_floats_survive(self):
        f = system_to_feature(FakeSystem(attrs={"core_max_dbz": 52.5}))
        assert f["properties"]["core_max_dbz"] == 52.5

    def test_numpy_scalar_becomes_python_float(self):
        np = pytest.importorskip("numpy")
        f = system_to_feature(FakeSystem(attrs={"mean": np.float32(12.5)}))
        assert isinstance(f["properties"]["mean"], float)

    def test_numpy_bool_becomes_python_bool(self):
        np = pytest.importorskip("numpy")
        f = system_to_feature(FakeSystem(attrs={"is_convective": np.bool_(True)}))
        assert f["properties"]["is_convective"] is True

    def test_none_attrs_survive(self):
        """c2_vertical is None when H0 was unavailable — not False."""
        f = system_to_feature(FakeSystem(attrs={"c2_vertical": None}))
        assert f["properties"]["c2_vertical"] is None

    def test_whole_feature_is_strict_json(self):
        np = pytest.importorskip("numpy")
        f = system_to_feature(FakeSystem(attrs={
            "a": np.float32("nan"), "b": np.float64(3.5), "c": "text",
        }))
        blob = json.dumps(f)
        assert "NaN" not in blob and "Infinity" not in blob


class TestDroppedAttrs:
    @pytest.mark.parametrize("key", ["raster", "nodata", "geotransform"])
    def test_raster_payload_is_dropped(self, key):
        """Per-system raster crops are large and useless over HTTP."""
        f = system_to_feature(FakeSystem(attrs={key: [1, 2, 3], "max": 1.0}))
        assert key not in f["properties"]


class TestGeometry:
    def test_geometry_is_parsed_not_embedded_as_string(self):
        f = system_to_feature(FakeSystem())
        assert f["geometry"]["type"] == "Polygon"

    def test_missing_geometry_yields_no_feature(self):
        system = FakeSystem()
        system.geom = None
        assert system_to_feature(system) is None

    def test_unserialisable_geometry_is_skipped(self):
        class Bad:
            def ExportToJson(self): raise RuntimeError("boom")
        assert system_to_feature(FakeSystem(geom=Bad())) is None


class TestSinkToFeatures:
    def test_systems_are_tagged_as_systems(self):
        sink = VolumeSink([9])
        sink.systems.output([FakeSystem()])
        assert sink_to_features(sink)[0]["properties"]["kind"] == "system"

    def test_forecasts_are_tagged_with_lead(self):
        sink = VolumeSink([9, 18])
        sink.forecasts[18].output([FakeSystem()])
        feat = sink_to_features(sink)[0]
        assert (feat["properties"]["kind"], feat["properties"]["lead_min"]) == ("forecast", 18)

    def test_systems_precede_forecasts(self):
        sink = VolumeSink([9])
        sink.systems.output([FakeSystem(name="s")])
        sink.forecasts[9].output([FakeSystem(name="f")])
        kinds = [f["properties"]["kind"] for f in sink_to_features(sink)]
        assert kinds == ["system", "forecast"]

    def test_empty_sink_yields_nothing(self):
        assert sink_to_features(VolumeSink([9])) == []


class TestBuildFrame:
    """A discarded volume must be distinguishable from a missing one."""

    def test_gate_failure_still_produces_a_frame(self):
        frame = build_frame(_ts(), FakeResultado(passed=False), VolumeSink([9]))
        assert frame["gate_passed"] is False

    def test_gate_failure_reports_the_diagnostic_numbers(self):
        frame = build_frame(_ts(), FakeResultado(passed=False), VolumeSink([9]))
        assert frame["gate"]["tope_max_m"] == 4800.0
        assert frame["gate"]["umbral_m"] == 4841.0

    def test_gate_failure_has_no_features(self):
        sink = VolumeSink([9])
        sink.systems.output([FakeSystem()])
        frame = build_frame(_ts(), FakeResultado(passed=False), sink)
        assert frame["features"]["features"] == []

    def test_passing_gate_includes_features(self):
        sink = VolumeSink([9])
        sink.systems.output([FakeSystem()])
        frame = build_frame(_ts(), FakeResultado(passed=True), sink)
        assert len(frame["features"]["features"]) == 1

    def test_counts_are_reported(self):
        frame = build_frame(_ts(), FakeResultado(), VolumeSink([9]))
        assert frame["counts"] == {
            "detected": 3, "convective": 2, "tracked": 1, "forecasts": 7
        }

    def test_timestamp_is_iso_z(self):
        frame = build_frame(_ts(), FakeResultado(), VolumeSink([9]))
        assert frame["timestamp"] == "2026-10-20T12:00:00Z"


class TestGateToDict:
    def test_non_finite_tope_becomes_null(self):
        """tope_max_m is -inf when the volume has no echo at all."""
        g = FakeGate()
        g.tope_max_m = -math.inf
        assert gate_to_dict(g)["tope_max_m"] is None

    def test_h0_source_is_preserved(self):
        """Needed to audit which volumes ran on model vs climatology."""
        assert gate_to_dict(FakeGate())["h0_fuente"] == "climatologia"


def _ts():
    from datetime import datetime, timezone
    return datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)
