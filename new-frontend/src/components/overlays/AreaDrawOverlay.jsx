// components/AreaDrawOverlay.jsx
import { useEffect } from "react";
import { useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet-draw/dist/leaflet.draw.css";
import "leaflet-draw"; // extiende L con controles de dibujo

// Parche para evitar error type en leaflet-draw
(function () {
  const Lg = window.L;
  if (!Lg?.GeometryUtil?.readableArea) return;

  const orig = Lg.GeometryUtil.readableArea;
  Lg.GeometryUtil.readableArea = function (
    area,
    isMetric = true,
    precision = 2
  ) {
    try {
      // Intento original
      return orig.call(this, area, isMetric, precision);
    } catch (err) {
      // Fallback seguro sin usar 'type'
      // area viene en m² si isMetric=true, sino convertimos a ft² aprox.
      const val = isMetric ? area : area * 10.7639;
      const unit = isMetric ? "m²" : "ft²";
      // redondeo simple (evita NPEs del código original)
      const prec = Number.isFinite(precision) ? precision : 2;
      // Elegí si querés ha o km² según magnitud
      if (isMetric && val > 1e6) {
        return `${(val / 1e6).toFixed(prec)} km²`;
      }
      return `${val.toFixed(prec)} ${unit}`;
    }
  };
})();

/**
 * Props:
 *  - enabled: boolean
 *  - onComplete: (geojson) => void
 *  - modes?: { polygon?: boolean, rectangle?: boolean }
 */
export default function AreaDrawOverlay({
  enabled,
  onComplete,
  modes = { polygon: true, rectangle: true },
}) {
  const map = useMap();

  useEffect(() => {
    if (!map || !enabled) return;

    // Configurar herramientas disponibles
    const drawOptions = {
      draw: {
        polygon: modes.polygon
          ? { allowIntersection: false, showArea: true }
          : false,
        rectangle: modes.rectangle ? {} : false,
        polyline: false,
        circle: false,
        marker: false,
        circlemarker: false,
      },
      edit: false,
    };

    const drawControl = new L.Control.Draw(drawOptions);
    map.addControl(drawControl);

    const onCreated = (e) => {
      const layer = e.layer;
      // GeoJSON con coords en lon/lat (Leaflet exporta GeoJSON en EPSG:4326)
      const gj = layer.toGeoJSON();
      // (Opcional) dejar visible el polígono. Si no querés, no lo agregues.
      layer.addTo(map);
      onComplete?.(gj, layer);
    };

    map.on(L.Draw.Event.CREATED, onCreated);

    // TIP: lanzar la herramienta inmediatamente (p. ej. rectángulo)
    const drawer = modes.rectangle
      ? new L.Draw.Rectangle(map)
      : new L.Draw.Polygon(map);
    drawer.enable();

    return () => {
      map.off(L.Draw.Event.CREATED, onCreated);
      try {
        map.removeControl(drawControl);
      } catch {}
    };
  }, [map, enabled, modes, onComplete]);

  return null;
}
