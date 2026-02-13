import { useEffect, useMemo, useRef, useState } from "react";
import {
  MapContainer,
  TileLayer,
  useMap,
  CircleMarker,
  Tooltip,
  Polyline,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";
import MapPickOverlay from "../overlays/MapPickOverlay";
import AreaDrawOverlay from "../overlays/AreaDrawOverlay";
import LineDrawOverlay from "../overlays/LineDrawOverlay";
import UsePixelStatClick from "../overlays/UsePixelStatClick";

function COGTile({
  tilejsonUrl,
  opacity,
  zIndex = 500,
  hasInitializedViewRef,
}) {
  const map = useMap();
  const [template, setTemplate] = useState(null);
  const [llb, setLLB] = useState(null);
  const [nativeZooms, setNativeZooms] = useState({ min: 0, max: 22 });
  const abortRef = useRef(null);

  useEffect(() => {
    if (!tilejsonUrl) return;

    // cancelar fetch previo si cambia rápido
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    (async () => {
      try {
        const r = await fetch(tilejsonUrl, {
          signal: ctrl.signal,
          keepalive: true,
          headers: {
            Connection: "keep-alive",
          },
        });
        if (!r.ok) {
          const txt = await r.text();
          console.error("TileJSON error", r.status, txt.slice(0, 200));
          return;
        }
        const tj = await r.json();

        let url = tj.tiles?.[0];
        if (!url) {
          console.error("TileJSON sin 'tiles':", tj);
          return;
        }
        // prefijo /cog si falta
        if (url.includes("/tiles/") && !url.includes("/cog/tiles/")) {
          url = url.replace("/tiles/", "/cog/tiles/");
        }
        // cache-buster estable basado en tilejsonUrl (no Date.now() para permitir cache de browser)
        const stableHash = tilejsonUrl
          .split("")
          .reduce((a, c) => ((a << 5) - a + c.charCodeAt(0)) | 0, 0);
        url +=
          (url.includes("?") ? "&" : "?") +
          "v=" +
          Math.abs(stableHash).toString(36);

        // zooms nativos
        const minN = Number.isFinite(tj.minzoom) ? tj.minzoom : 0;
        const maxN = Number.isFinite(tj.maxzoom) ? tj.maxzoom : 22;
        setNativeZooms({ min: minN, max: maxN });

        // bounds / center
        if (Array.isArray(tj.bounds) && tj.bounds.length === 4) {
          // Solo centrar el mapa la primera vez que se carga una capa
          if (
            Array.isArray(tj.center) &&
            tj.center.length === 3 &&
            hasInitializedViewRef &&
            !hasInitializedViewRef.current
          ) {
            const [lon, lat, z] = tj.center;
            map.setView([lat, lon], z);
            hasInitializedViewRef.current = true;
          }
          const [w, s, e, n] = tj.bounds;
          const bounds = [
            [s, w],
            [n, e],
          ];
          setLLB(bounds);

          // map.fitBounds(bounds, { padding: [20, 20] })
          // map.setMaxBounds(bounds);
        }

        setTemplate(url);
      } catch (e) {
        if (e.name !== "AbortError") console.error("TileJSON fetch fail:", e);
      }
    })();

    return () => {
      ctrl.abort();
      // liberar maxBounds al cambiar de producto
      try {
        map.setMaxBounds(null);
      } catch {
        console.warn("Error al limpiar maxBounds");
      }
    };
  }, [tilejsonUrl, map]);

  // clave estable para forzar desmontaje limpio de la capa previa
  const layerKey = template
    ? `${template}|${nativeZooms.min}|${nativeZooms.max}`
    : "none";

  return template ? (
    <TileLayer
      key={layerKey}
      url={template}
      opacity={opacity}
      noWrap={true}
      bounds={llb}
      minNativeZoom={nativeZooms.min}
      maxNativeZoom={nativeZooms.max}
      zIndex={zIndex}
      // Optimizaciones de carga de tiles
      updateWhenIdle={true} // Actualiza mientras mueves el mapa
      updateWhenZooming={true} // Actualiza durante zoom animado (más responsive)
      updateInterval={200} // 200ms entre actualizaciones (más responsivo)
      keepBuffer={4} // Mantiene 4 tiles de buffer fuera del viewport
      tileSize={256} // Tamaño estándar de tiles
      reuseTiles={true} // Reutiliza tiles ya cargadas
      // tile transparente en caso de error puntual
      errorTileUrl="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="
      eventHandlers={{
        tileerror: (e) => console.warn("tileerror", e.coords, e.error),
      }}
      crossOrigin={"anonymous"}
    />
  ) : null;
}

export default function MapView({
  overlayData,
  opacities = [0.95],
  opacityByField = {},
  pickPointMode = false,
  radarSite = null,
  pickedPoint = null,
  onPickPoint,
  drawAreaMode = false,
  onAreaComplete,
  pixelStatMode = false,
  onPixelStatClick,
  pixelStatMarker = null,
  lineOverlay = null,
  onClearLineOverlay,
  rhiEndpoints = null, // { start: {lat, lon}, end: {lat, lon} }
  activeToolFile = null, // radar seleccionado para herramientas
  onMapReady, // Callback para recibir la instancia del mapa
  baseMapUrl = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", // URL del mapa base
  baseMapAttribution = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  // Props para perfil de elevación
  lineDrawMode = false,
  drawnLineCoords = [],
  onLineComplete,
  onLinePointsChange,
  highlightedPoint = null,
}) {
  const center = useMemo(() => [-31.4, -64.2], []);
  const baseZ = 500;
  // overlayData ahora puede ser un array de capas de distintos radares para el frame actual
  const n = overlayData?.length ?? 0;

  // Ref compartido para controlar si ya se inicializó la vista del mapa
  const hasInitializedViewRef = useRef(false);

  // Si pickedPoint se limpia, avisar al padre para limpiar la línea
  useEffect(() => {
    if (!pickedPoint && typeof onClearLineOverlay === "function") {
      onClearLineOverlay();
    }
  }, [pickedPoint]);

  // Componente interno para acceder a la instancia del mapa
  function MapReadyHandler() {
    const map = useMap();
    useEffect(() => {
      if (onMapReady && map) {
        onMapReady(map);
      }
    }, [map]);
    return null;
  }

  return (
    <MapContainer
      center={center}
      zoom={6}
      style={{ height: "100vh", width: "100%" }}
      worldCopyJump={false}
      preferCanvas={false}
      fadeAnimation={false}
      zoomAnimation={true}
      markerZoomAnimation={true}
    >
      <MapReadyHandler />
      <TileLayer
        key={baseMapUrl}
        url={baseMapUrl}
        attribution={baseMapAttribution}
      />

      {/* Mostrar todas las capas del frame actual (pueden ser de distintos radares) */}
      {Array.isArray(overlayData) &&
        overlayData.map((L, idx) => {
          const keyField = String(L.field || L.label || "").toUpperCase();
          const fieldOpacity =
            typeof opacityByField[keyField] === "number"
              ? opacityByField[keyField]
              : opacities[idx] ?? 1;

          // Las capas del radar seleccionado se muestran arriba (mayor zIndex)
          // El orden en el array es bottom-to-top, así que invertimos idx para zIndex
          const isActiveRadar =
            activeToolFile && L.source_file === activeToolFile;
          const zIndex = isActiveRadar
            ? baseZ + 1000 + (n - 1 - idx) * 10 // radar activo: zIndex muy alto, orden invertido
            : baseZ + (n - 1 - idx) * 10; // otros radares: zIndex normal, orden invertido

          return (
            <COGTile
              key={`${L.field || "layer"}|${L.tilejson_url}`}
              tilejsonUrl={L.tilejson_url}
              opacity={fieldOpacity}
              zIndex={zIndex}
              hasInitializedViewRef={hasInitializedViewRef}
            />
          );
        })}
      <MapPickOverlay
        enabled={pickPointMode}
        pickedPoint={pickedPoint}
        onPick={onPickPoint}
      />
      <AreaDrawOverlay
        enabled={drawAreaMode}
        onComplete={onAreaComplete}
        modes={{ polygon: true, rectangle: true }}
      />
      <LineDrawOverlay
        enabled={lineDrawMode}
        points={drawnLineCoords}
        onComplete={onLineComplete}
        onPointsChange={onLinePointsChange}
      />
      <UsePixelStatClick
        enabled={pixelStatMode}
        onPixelStatClick={onPixelStatClick}
      />
      {pixelStatMarker &&
        Number.isFinite(pixelStatMarker.lat) &&
        Number.isFinite(pixelStatMarker.lon) && (
          <CircleMarker
            center={[pixelStatMarker.lat, pixelStatMarker.lon]}
            radius={6}
            pathOptions={{ color: "#ff3b30", weight: 2, fillOpacity: 0.7 }}
          >
            <Tooltip direction="top" offset={[0, -6]} permanent>
              {pixelStatMarker.value == null
                ? "masked"
                : String(pixelStatMarker.value)}
            </Tooltip>
          </CircleMarker>
        )}
      {/* Marcadores persistentes para los puntos de RHI (inicio/fin) */}
      {rhiEndpoints?.start &&
        Number.isFinite(rhiEndpoints.start.lat) &&
        Number.isFinite(rhiEndpoints.start.lon) && (
          <CircleMarker
            center={[rhiEndpoints.start.lat, rhiEndpoints.start.lon]}
            radius={6}
            pathOptions={{ color: "#00aaff", weight: 2, fillOpacity: 0.7 }}
          />
        )}
      {rhiEndpoints?.end &&
        Number.isFinite(rhiEndpoints.end.lat) &&
        Number.isFinite(rhiEndpoints.end.lon) && (
          <CircleMarker
            center={[rhiEndpoints.end.lat, rhiEndpoints.end.lon]}
            radius={6}
            pathOptions={{ color: "#00aaff", weight: 2, fillOpacity: 0.7 }}
          />
        )}
      {Array.isArray(lineOverlay) && lineOverlay.length === 2 && (
        <Polyline
          positions={lineOverlay}
          pathOptions={{ color: "#00aaff", weight: 3, opacity: 0.9 }}
        />
      )}
      {/* Origen del radar (solo al elegir puntos para pseudo-RHI) */}
      {pickPointMode && radarSite && (
        <CircleMarker
          center={[radarSite.lat, radarSite.lon]}
          radius={7}
          pathOptions={{
            color: "#ff9800",
            weight: 3,
            fillOpacity: 0.9,
            fillColor: "#ff9800",
          }}
        >
          <Tooltip direction="top" offset={[0, -6]} permanent>
            Origen radar
          </Tooltip>
        </CircleMarker>
      )}
      {/* Punto resaltado al hacer hover en el gráfico de elevación */}
      {highlightedPoint &&
        Number.isFinite(highlightedPoint.lat) &&
        Number.isFinite(highlightedPoint.lon) && (
          <CircleMarker
            center={[highlightedPoint.lat, highlightedPoint.lon]}
            radius={8}
            pathOptions={{
              color: "#ff0000",
              weight: 3,
              fillOpacity: 0.9,
              fillColor: "#ff0000",
            }}
          >
            <Tooltip direction="top" offset={[0, -8]} permanent>
              Punto actual
            </Tooltip>
          </CircleMarker>
        )}
    </MapContainer>
  );
}
