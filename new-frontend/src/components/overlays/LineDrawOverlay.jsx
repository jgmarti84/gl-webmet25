import { useEffect, useRef, useState } from "react";
import { useMap, Polyline, CircleMarker, Marker } from "react-leaflet";
import L from "leaflet";

// Crear icono personalizado para el marcador final (cuadrado blanco)
const finishMarkerIcon = L.divIcon({
  className: "finish-marker",
  html: '<div style="width: 16px; height: 16px; background: white; border: 3px solid #ff6b35; cursor: pointer;"></div>',
  iconSize: [16, 16],
  iconAnchor: [8, 8],
});

/**
 * Overlay para dibujar una línea poligonal en el mapa.
 * El usuario hace click para agregar puntos.
 * El último punto es un cuadrado blanco, al hacer click en él se finaliza el dibujo.
 *
 * Props:
 *  - enabled: boolean
 *  - points: {lat, lon}[] - puntos externos (controlado desde padre)
 *  - onComplete: (coordinates: {lat, lon}[]) => void - cuando el usuario termina de dibujar
 *  - onPointsChange: (coordinates: {lat, lon}[]) => void - cuando se agregan/quitan puntos
 */
export default function LineDrawOverlay({
  enabled,
  points: externalPoints,
  onComplete,
  onPointsChange,
}) {
  const map = useMap();
  const [points, setPoints] = useState([]);
  const onCompleteRef = useRef(onComplete);
  const onPointsChangeRef = useRef(onPointsChange);

  // Sincronizar con puntos externos (reseteo desde padre)
  useEffect(() => {
    if (externalPoints !== undefined) {
      setPoints(externalPoints);
    }
  }, [externalPoints]);

  // Limpiar estado visual cuando se desactiva
  useEffect(() => {
    if (!enabled && points.length > 0) {
      // Si se desactiva con puntos existentes, mantenerlos visibles
      // pero no permitir edición
    }
  }, [enabled, points]);

  // Mantener refs actualizadas sin causar re-renders
  useEffect(() => {
    onCompleteRef.current = onComplete;
    onPointsChangeRef.current = onPointsChange;
  }, [onComplete, onPointsChange]);

  // Notificar cambios en los puntos (fuera del render)
  useEffect(() => {
    if (enabled && points.length > 0) {
      onPointsChangeRef.current?.(points);
    }
  }, [points, enabled]);

  useEffect(() => {
    if (!map || !enabled) {
      return;
    }

    // Cambiar cursor para indicar modo dibujo
    map.getContainer().style.cursor = "crosshair";

    const handleMapClick = (e) => {
      // Agregar punto
      const newPoint = { lat: e.latlng.lat, lon: e.latlng.lng };
      setPoints((prev) => [...prev, newPoint]);
    };

    const handleKeyDown = (e) => {
      // ESC para cancelar
      if (e.key === "Escape") {
        setPoints([]);
        onPointsChangeRef.current?.([]);
      }
      // Enter para terminar (si hay al menos 2 puntos)
      if (e.key === "Enter") {
        setPoints((prevPoints) => {
          if (prevPoints.length >= 2) {
            onCompleteRef.current?.(prevPoints);
          }
          return prevPoints; // Mantener los puntos visibles
        });
      }
      // Delete último punto con tecla Delete
      if (e.key === "Delete") {
        setPoints((prev) => {
          if (prev.length > 0) {
            const newPoints = prev.slice(0, -1);
            // Notificar al padre del cambio
            onPointsChangeRef.current?.(newPoints);
            return newPoints;
          }
          return prev;
        });
      }
    };

    map.on("click", handleMapClick);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      map.off("click", handleMapClick);
      document.removeEventListener("keydown", handleKeyDown);
      map.getContainer().style.cursor = "";
    };
  }, [map, enabled]);

  // Función para finalizar el dibujo al hacer click en el marcador final
  const handleFinishClick = () => {
    if (points.length >= 2) {
      onCompleteRef.current?.(points);
      // No limpiamos los puntos - se mantienen visibles hasta cerrar el diálogo
    }
  };

  if (!enabled || points.length === 0) return null;

  // Convertir puntos para Leaflet (formato [lat, lon])
  const positions = points.map((p) => [p.lat, p.lon]);

  return (
    <>
      {/* Línea conectando los puntos */}
      {points.length > 1 && (
        <Polyline
          positions={positions}
          color="#ff6b35"
          weight={3}
          opacity={0.8}
          dashArray="5, 10"
        />
      )}

      {/* Marcadores en cada punto (excepto el último) */}
      {points.slice(0, -1).map((point, idx) => (
        <CircleMarker
          key={idx}
          center={[point.lat, point.lon]}
          radius={6}
          fillColor={idx === 0 ? "#00ff00" : "#ff6b35"}
          fillOpacity={0.9}
          color="#fff"
          weight={2}
        />
      ))}

      {/* Marcador final (cuadrado blanco clickeable) - solo si hay al menos 2 puntos */}
      {points.length >= 1 && (
        <Marker
          position={[
            points[points.length - 1].lat,
            points[points.length - 1].lon,
          ]}
          icon={finishMarkerIcon}
          eventHandlers={{
            click: handleFinishClick,
          }}
        />
      )}
    </>
  );
}
