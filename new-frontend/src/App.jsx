import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { useSnackbar } from "notistack";
import {
  uploadFile,
  processFile,
  generatePseudoRHI,
  generateAreaStats,
  generatePixelStat,
  generateElevationProfile,
} from "./api/backend";
import { registerCleanupAxios } from "./api/registerCleanupAxios";
import stableStringify from "json-stable-stringify";
import { useMapActions } from "./hooks/useMapActions";
import { useDownloads } from "./hooks/useDownloads";
import "./print.css";

import { generateSessionId } from "./utils/session";
import UploadButton from "./components/ui/UploadButton";
import HeaderCard from "./components/ui/HeaderCard";
import Alerts from "./components/ui/Alerts";
import Loader from "./components/ui/Loader";
import SplitScreenContainer from "./components/layout/SplitScreenContainer";

// Utilidad para combinar frames de múltiples radares por timestamp
function mergeRadarFrames(results, toleranceSec = 240) {
  // results: [{ radar, outputs: [[LayerResult,...], ...] }, ...]

  // 1) aplanamos a una lista de {tsISO, radar, layers}
  const shots = [];
  for (const r of results || []) {
    for (const layers of r.outputs || []) {
      const rawTs = layers?.[0]?.timestamp ?? null; // todos los layers del frame comparten ts
      const tsISO = rawTs
        ? new Date(rawTs).toISOString() // normalizamos SIEMPRE a ISO
        : null;
      // Anotar el radar en cada layer para uso posterior
      const layersWithRadar = layers.map((layer) => ({
        ...layer,
        radar: r.radar,
      }));
      shots.push({ tsISO, radar: r.radar, layers: layersWithRadar });
    }
  }

  // 2) agrupamos por "bucket temporal" con tolerancia
  const buckets = []; // [{ center: Date, members: [layers,...] }]
  const tolMs = toleranceSec * 1000;

  const tryPutInBucket = (ts, layers) => {
    if (!ts) {
      buckets.push({ center: null, members: [layers] }); // sin timestamp: bucket propio
      return;
    }
    const t = new Date(ts).getTime();
    for (const b of buckets) {
      if (b.center === null) continue;
      const dt = Math.abs(b.center.getTime() - t);
      if (dt <= tolMs) {
        b.members.push(layers);
        return;
      }
    }
    // no encontró bucket compatible → crear uno nuevo
    buckets.push({ center: new Date(t), members: [layers] });
  };

  for (const s of shots) {
    tryPutInBucket(s.tsISO, s.layers);
  }

  // 3) ordenar buckets por tiempo (los null al final)
  buckets.sort((a, b) => {
    if (a.center === null && b.center === null) return 0;
    if (a.center === null) return 1;
    if (b.center === null) return -1;
    return a.center - b.center;
  });

  // 4) salida: cada bucket → un “frame” con todas las capas mezcladas (multi-radar)
  //    mantenemos el orden interno de cada frame por 'order' (ya viene en cada LayerResult)
  return buckets.map((b) =>
    b.members
      .flat()
      .slice()
      .sort((L, R) => (L.order ?? 0) - (R.order ?? 0))
  );
}

function buildComputeKey({
  files,
  product,
  fields,
  elevation,
  height,
  filters,
  selectedVolumes,
  selectedRadars,
  colormap_overrides,
}) {
  return stableStringify({
    files,
    product,
    fields,
    elevation,
    height,
    filters,
    selectedVolumes,
    selectedRadars,
    colormap_overrides,
  });
}

export default function App() {
  const [overlayData, setOverlayData] = useState({
    outputs: [],
    animation: false,
    metadata: {},
  });
  const [opacity, setOpacity] = useState([0.95]);
  const [opacityByField, setOpacityByField] = useState({});
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0); // índice de la imagen activa
  const [loading, setLoading] = useState(false);
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [fieldsUsed, setFieldsUsed] = useState(["DBZH"]);
  const [filesInfo, setFilesInfo] = useState([]);
  const [volumes, setVolumes] = useState([]); // lista de volúmenes cargados sin repetidos
  const [availableRadars, setAvailableRadars] = useState([]); // todos los radares presentes en archivos subidos
  const [savedLayers, setSavedLayers] = useState([]); // layers / variables usadas
  const [filtersUsed, setFiltersUsed] = useState([]); // filtros aplicados
  const [activeElevation, setActiveElevation] = useState(null);
  const [activeHeight, setActiveHeight] = useState(null);
  const allCogsRef = useRef(new Set());
  // animación controlada por variable 'animation' derivada de outputs
  const [computeKey, setComputeKey] = useState("");
  const [warnings, setWarnings] = useState([]);
  // var currentOverlay = overlayData.outputs?.[currentIndex] || null;
  const [mapInstance, setMapInstance] = useState(null); // Referencia al mapa Leaflet

  const [alert, setAlert] = useState({
    open: false,
    message: "",
    severity: "info",
  });

  const { enqueueSnackbar } = useSnackbar();

  // Session ID único para esta pestaña/ventana del navegador
  const [sessionId] = useState(() => generateSessionId());

  const [pixelStatMode, setPixelStatMode] = useState(false);
  const [pixelStatMarker, setPixelStatMarker] = useState(null);
  const [rhiOpen, setRhiOpen] = useState(false);
  const [pickPointMode, setPickPointMode] = useState(false);
  const [pickedPoint, setPickedPoint] = useState(null); // { lat, lon } seleccionado
  const [rhiLinePreview, setRhiLinePreview] = useState({
    start: null,
    end: null,
  });
  const [areaDrawMode, setAreaDrawMode] = useState(false);
  const [areaPolygon, setAreaPolygon] = useState(null);
  const [areaStatsOpen, setAreaStatsOpen] = useState(false);
  const drawnLayerRef = useRef(null); // referencia a la capa dibujada
  // archivo seleccionado manualmente para herramientas (pixel/área/RHI)
  const [activeToolFile, setActiveToolFile] = useState(null);
  // Estado para el selector de mapas base
  const [mapSelectorOpen, setMapSelectorOpen] = useState(false);
  // Estado para el perfil de elevación
  const [elevationProfileOpen, setElevationProfileOpen] = useState(false);
  const [lineDrawMode, setLineDrawMode] = useState(false);
  const [drawnLineCoords, setDrawnLineCoords] = useState([]);
  const [lineDrawingFinished, setLineDrawingFinished] = useState(false);
  const [highlightedPoint, setHighlightedPoint] = useState(null);
  const [selectedBaseMap, setSelectedBaseMap] = useState({
    id: "osm",
    name: "Argenmap",
    url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  });
  // Estado para paletas de colores personalizadas por campo
  const [selectedColormaps, setSelectedColormaps] = useState({});
  const [initialColormaps, setInitialColormaps] = useState({});
  const [paletteSelectorOpen, setPaletteSelectorOpen] = useState(false);
  const [layerManagerOpen, setLayerManagerOpen] = useState(false);

  // Estado para split screen
  const [splitScreenActive, setSplitScreenActive] = useState(false);

  // Derivar sitio del radar a partir del archivo activo o el archivo actual en visualización
  const radarSite = useMemo(() => {
    const fileToUse = activeToolFile || uploadedFiles[currentIndex];
    if (!fileToUse) return null;
    // Buscar metadata del archivo
    const fi = filesInfo.find((f) => f.filepath === fileToUse);
    const md = fi?.metadata;
    if (!md) return null;
    const site = md.radar_site || md.site; // soportar ambos nombres
    if (!site || site.lat == null || site.lon == null) return null;
    return {
      lat: Number(site.lat),
      lon: Number(site.lon),
      alt_m: site.alt_m ?? site.alt ?? null,
    };
  }, [activeToolFile, uploadedFiles, currentIndex, filesInfo]);

  // Hook para acciones del mapa (screenshot, print, fullscreen)
  const { isFullscreen, handleScreenshot, handlePrint, handleFullscreen } =
    useMapActions();

  // Hook para gestión de descargas
  const { downloadFile, generateFilename } = useDownloads();

  // Registrar cleanup en cierre de pestaña/ventana
  useEffect(() => {
    const unregister = registerCleanupAxios(() => ({
      uploads: uploadedFiles,
      cogs: Array.from(allCogsRef.current),
      delete_cache: true,
      session_id: sessionId,
    }));
    return unregister;
  }, [uploadedFiles, overlayData, sessionId]);

  // Seteamos currentOverlay
  // Si la respuesta tiene results (multi-radar), combinamos los frames por timestamp
  // sino dejamos la respuesta vieja
  let mergedOutputs = [];
  let animation = false;
  let product = overlayData.product || "PPI";
  // const product = overlayData.product;
  if (overlayData.results) {
    mergedOutputs = mergeRadarFrames(overlayData.results);
    animation = mergedOutputs.length > 1;
  } else {
    mergedOutputs = overlayData.outputs || [];
    animation = overlayData.animation;
  }
  var currentOverlay = mergedOutputs[currentIndex] || null;

  // Sincronizar archivo activo con las capas visibles del frame actual
  // Solo se setea activeToolFile cuando hay múltiples RADARES diferentes (no múltiples fields del mismo radar)
  useEffect(() => {
    if (!Array.isArray(currentOverlay) || currentOverlay.length === 0) {
      setActiveToolFile(null);
      return;
    }

    // Usar la información del radar que ya viene anotada desde mergeRadarFrames
    const radarNames = [
      ...new Set(currentOverlay.map((L) => L?.radar).filter(Boolean)),
    ];
    const sources = currentOverlay.map((L) => L?.source_file).filter(Boolean);

    // Solo setear activeToolFile si hay múltiples radares diferentes
    if (radarNames.length > 1) {
      // Múltiples radares: setear activeToolFile al primero (o mantener el actual si está en la lista)
      setActiveToolFile((prev) =>
        prev && sources.includes(prev) ? prev : sources[0]
      );
    } else {
      // Un solo radar (aunque tenga múltiples fields): NO setear activeToolFile
      setActiveToolFile(null);
    }
  }, [currentOverlay]);

  // Función para descargar COGs de las capas actuales
  const handleDownloadCOGs = useCallback(async () => {
    if (!currentOverlay || currentOverlay.length === 0) {
      enqueueSnackbar("No hay capas disponibles para descargar", {
        variant: "warning",
      });
      return;
    }

    try {
      // Filtrar capas: solo las del radar activo (activeToolFile)
      // Esto permite descargar todos los fields del radar activo, pero no de otros radares
      const layersToDownload = currentOverlay.filter((layer) => {
        if (!layer.image_url) return false;

        // Si hay activeToolFile, solo descargar capas de ese radar
        if (activeToolFile && layer.source_file) {
          return layer.source_file === activeToolFile;
        }

        // Si no hay activeToolFile, descargar todas las capas con image_url
        return true;
      });

      if (layersToDownload.length === 0) {
        enqueueSnackbar("No hay archivos COG para descargar", {
          variant: "warning",
        });
        return;
      }

      // Crear todos los links de descarga
      const baseUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";
      const downloadLinks = [];

      for (const layer of layersToDownload) {
        const filename =
          layer.image_url.split("/").pop() || generateFilename("cog", ".tif");
        const cogUrl = `${baseUrl}/${layer.image_url}`;

        try {
          const response = await fetch(cogUrl);
          if (!response.ok) {
            console.error(
              `Error descargando ${filename}: HTTP ${response.status}`
            );
            continue;
          }

          const blob = await response.blob();
          const url = window.URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = filename;
          link.style.display = "none";
          document.body.appendChild(link);
          downloadLinks.push({ link, url });
        } catch (err) {
          console.error(`Error preparando descarga de ${filename}:`, err);
        }
      }

      // Hacer click en todos los links con pequeños delays
      for (let i = 0; i < downloadLinks.length; i++) {
        downloadLinks[i].link.click();
        if (i < downloadLinks.length - 1) {
          await new Promise((resolve) => setTimeout(resolve, 300));
        }
      }

      // Limpiar después de un delay final
      setTimeout(() => {
        downloadLinks.forEach(({ link, url }) => {
          document.body.removeChild(link);
          window.URL.revokeObjectURL(url);
        });
      }, 1000);

      enqueueSnackbar(`${downloadLinks.length} archivo(s) COG descargado(s)`, {
        variant: "success",
      });
    } catch (error) {
      console.error("Error descargando COGs:", error);
      enqueueSnackbar("Error al descargar archivos COG", { variant: "error" });
    }
  }, [currentOverlay, activeToolFile, generateFilename, enqueueSnackbar]);

  // Configurar descargas disponibles para el toolbar
  const availableDownloads = useMemo(() => {
    const downloads = {};

    // Captura del mapa (siempre disponible si hay mapa)
    if (mapInstance) {
      downloads.mapScreenshot = {
        handler: () => handleScreenshot(mapInstance, "map-container"),
        label: "Captura del mapa",
        disabled: false,
      };
    }

    // Descargar COGs de capas actuales
    if (currentOverlay && currentOverlay.length > 0) {
      downloads.cogLayers = {
        //mostrar el nombre del archivo activo si hay uno  no todo el path d:/...
        handler: handleDownloadCOGs,
        label: activeToolFile
          ? `Descargar capa de radar seleccionado`
          : `Descargar ${currentOverlay.length} capa(s) Geotiff`,
        disabled: false,
      };
    }

    return downloads;
  }, [mapInstance, currentOverlay, handleScreenshot, handleDownloadCOGs]);

  const handleFileUpload = () => {
    document.getElementById("upload-file").click();
  };

  const handleFilesSelected = async (files) => {
    try {
      setLoading(true);
      const uploadResp = await uploadFile(files, sessionId);
      const warnings = uploadResp.data.warnings || [];
      const filesInfo = uploadResp.data.files || [];
      const filepaths = filesInfo.map((f) => f.filepath);

      if (filesInfo.length === 0) {
        setAlert({
          open: true,
          message: "No se encontraron archivos válidos\n" + warnings.join("\n"),
          severity: "warning",
        });
        return;
      }
      if (warnings.length > 0) {
        setAlert({
          open: true,
          message: warnings.join("\n"),
          severity: "warning",
        });
      }
      setFilesInfo(filesInfo);
      setVolumes((prev) => {
        const merged = [...prev, ...uploadResp.data.volumes];
        return Array.from(new Set(merged));
      });
      setAvailableRadars((prev) => {
        const merged = [...prev, ...uploadResp.data.radars];
        return Array.from(new Set(merged));
      });
      setUploadedFiles((prev) => {
        const merged = [...prev, ...filepaths];
        // elimina duplicados preservando el orden
        return Array.from(new Set(merged));
      });
      setSelectorOpen(true);
    } catch (err) {
      setAlert({
        open: true,
        message: err.response?.data?.error || "Error",
        severity: "error",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleProductChosen = async (data) => {
    if (!uploadedFiles || uploadedFiles.length === 0) {
      setAlert({
        open: true,
        message: "No hay archivos para procesar",
        severity: "error",
      });
      return;
    }
    try {
      setLoading(true);

      const files = uploadedFiles;
      const layers = data.layers;
      const product = data.product;
      const height = data.height;
      const elevation = data.elevation;
      const filters = data.filters;
      const selectedVolumes = data.selectedVolumes;
      const selectedRadars = data.selectedRadars;
      const enabledLayers = layers.filter((l) => l.enabled).map((l) => l.label);
      const enabledLayerObjs = layers.filter((l) => l.enabled);
      const opacities = enabledLayerObjs.map((l) => l.opacity);

      // Build field-based opacity map so all radars for the same field share opacity
      const opacityMap = Object.fromEntries(
        enabledLayerObjs.map((l) => [
          String(l.label || l.field).toUpperCase(),
          Number(l.opacity ?? 1),
        ])
      );

      setOpacity(opacities);
      setOpacityByField(opacityMap);
      setFieldsUsed(enabledLayers);
      setSavedLayers(data.layers);
      setFiltersUsed(filters);
      if (elevation !== undefined) setActiveElevation(elevation);

      // Reset height to null when product is not CAPPI
      if (height !== undefined) {
        setActiveHeight(height);
      } else {
        setActiveHeight(null);
      }

      const nextKey = buildComputeKey({
        files: uploadedFiles,
        product,
        fields: enabledLayers,
        elevation,
        height,
        filters,
        selectedVolumes,
        selectedRadars,
        colormap_overrides: selectedColormaps,
      });

      // Si solo cambió UI (opacidad/orden), no reproceses:
      if (nextKey === computeKey) {
        return;
      }

      const processResp = await processFile({
        files,
        layers: enabledLayers,
        product,
        height,
        elevation,
        filters,
        selectedVolumes,
        selectedRadars,
        colormap_overrides: selectedColormaps,
        session_id: sessionId,
      });
      if (
        !processResp.data ||
        !processResp.data.outputs ||
        processResp.data.outputs.length === 0
      ) {
        setAlert({
          open: true,
          message: "No se encontraron imágenes procesadas",
          severity: "warning",
        });
      }
      setOverlayData(processResp.data);
      setWarnings(processResp.data.warnings || []);
      setCurrentIndex(0);
      setComputeKey(nextKey);
      // Guardar las paletas usadas como "iniciales" para futuras comparaciones
      setInitialColormaps({ ...selectedColormaps });
      // Animación se calcula dinámicamente más abajo
      // Animación se calcula dinámicamente más abajo

      // Guardar todos los cogs para el cleanup
      // const fromOutputs = cogFsPaths(processResp.data?.outputs || []);
      // fromOutputs.forEach((p) => allCogsRef.current.add(p));

      setAlert({
        open: true,
        message: `Mostrando ${data.product.toUpperCase()}`,
        severity: "success",
      });
    } catch (err) {
      console.error(err);
      setAlert({
        open: true,
        message: "Error al procesar producto",
        severity: "error",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleOpenRHI = () => setRhiOpen(true);

  const handleRequestPickPoint = () => {
    // Activar modo pick point en el mapa para el RHI
    setPickedPoint(null);
    setPickPointMode(true);
  };
  const handlePickPoint = (pt) => {
    setPickedPoint(pt);
    // No desactivar pickPointMode aquí - se maneja desde PseudoRHIDialog
    // No modificar rhiLinePreview aquí - lo maneja PseudoRHIDialog vía onLinePreviewChange
  };
  const handleClearPickedPoint = () => {
    setPickedPoint(null);
    setPickPointMode(false); // Desactivar cuando se limpia
    setRhiLinePreview({ start: null, end: null });
  };

  // Callback para limpiar la línea cuando se limpian los puntos
  const handleClearLineOverlay = () => {
    setRhiLinePreview({ start: null, end: null });
  };

  const handleGenerateRHI = async ({
    filepath,
    field,
    end_lat,
    end_lon,
    start_lat,
    start_lon,
    filters,
    max_length_km,
    max_height_km,
    // max_length_km,
    // elevation,
  }) => {
    const resp = await generatePseudoRHI({
      filepath,
      field,
      end_lat,
      end_lon,
      start_lat,
      start_lon,
      filters,
      max_length_km,
      max_height_km,
      colormap_overrides: selectedColormaps,
      session_id: sessionId,
    });
    // devolvemos lo que el dialog espera
    return resp.data;
  };

  const handleOpenAreaStatsMode = () => {
    setAreaPolygon(null);
    setAreaDrawMode(true);
  };

  const handleAreaComplete = (gj, layer) => {
    drawnLayerRef.current = layer;
    setAreaDrawMode(false);
    setAreaPolygon(gj);
    setAreaStatsOpen(true);
  };

  const handleCloseAreaStats = () => {
    // al cerrar el diálogo, removemos la capa del mapa
    try {
      drawnLayerRef.current?.remove();
    } catch {
      console.log("Error");
    }
    drawnLayerRef.current = null;
    setAreaStatsOpen(false);
  };

  const handleAreaStatsRequest = async (payload) => {
    // backend espera: filepath, field, product, elevation?, height?, filters?, polygon
    const r = await generateAreaStats({ ...payload, session_id: sessionId });
    return r.data;
  };

  const handleTogglePixelStat = () => {
    setPixelStatMode((v) => {
      const next = !v;
      if (!next) setPixelStatMarker(null);
      return next;
    });
  };

  const handleToggleMapSelector = () => {
    setMapSelectorOpen((prev) => !prev);
  };

  const handleSelectBaseMap = (map) => {
    setSelectedBaseMap(map);
  };

  // Handlers para selector de paletas de color
  const handleTogglePaletteSelector = () => {
    setPaletteSelectorOpen((prev) => !prev);
  };

  const handleSelectColormap = (field, colormap) => {
    setSelectedColormaps((prev) => ({
      ...prev,
      [field]: colormap,
    }));
  };

  // Handler para aplicar cambios de paleta (reprocesar)
  const handleApplyColormaps = () => {
    // Cerrar el selector de paletas
    setPaletteSelectorOpen(false);
    // Abrir el ProductSelectorDialog para reprocesar con las nuevas paletas
    setSelectorOpen(true);
  };

  // Handlers para gestor de capas
  const handleToggleLayerManager = () => {
    setLayerManagerOpen((prev) => !prev);
  };

  const handleLayerReorder = (reorderedLayers) => {
    // Actualizar el orden de las capas en currentOverlay
    // Asignar nuevo 'order' basado en el índice
    const updatedLayers = reorderedLayers.map((layer, idx) => ({
      ...layer,
      order: idx,
    }));

    // Extraer el orden de los campos
    const fieldOrder = updatedLayers.map((l) => l.field);
    const uniqueFields = [...new Set(fieldOrder)];

    // Actualizar savedLayers para sincronizar con ProductSelectorDialog
    // Mantener TODOS los campos (habilitados y deshabilitados) pero reordenar los habilitados
    const reorderedSavedLayers = [];

    // Primero agregar los campos activos en el nuevo orden
    uniqueFields.forEach((field) => {
      const existingLayer = savedLayers.find(
        (l) => l.field === field || l.label === field
      );
      if (existingLayer) {
        reorderedSavedLayers.push(existingLayer);
      }
    });

    // Luego agregar los campos deshabilitados que no están en el nuevo orden
    savedLayers.forEach((layer) => {
      const isInNewOrder =
        uniqueFields.includes(layer.field) ||
        uniqueFields.includes(layer.label);
      if (!isInNewOrder) {
        reorderedSavedLayers.push(layer);
      }
    });

    if (reorderedSavedLayers.length > 0) {
      setSavedLayers(reorderedSavedLayers);
    }

    // Actualizar activeToolFile si cambió el primer radar
    if (updatedLayers.length > 0) {
      const firstRadarFile = updatedLayers[0].source_file;
      if (firstRadarFile !== activeToolFile) {
        setActiveToolFile(firstRadarFile);
      }
    }

    // Actualizar TODOS los frames con el nuevo orden
    // Aplicar el orden a todas las capas de todos los frames
    const updatedOutputs = mergedOutputs.map((frame) => {
      if (!Array.isArray(frame)) return frame;

      // Reordenar las capas de este frame según el nuevo orden
      const reordered = [...frame].sort((a, b) => {
        const aIdx = updatedLayers.findIndex(
          (l) => l.field === a.field && l.source_file === a.source_file
        );
        const bIdx = updatedLayers.findIndex(
          (l) => l.field === b.field && l.source_file === b.source_file
        );

        // Si no se encuentra, mantener al final
        if (aIdx === -1 && bIdx === -1) return 0;
        if (aIdx === -1) return 1;
        if (bIdx === -1) return -1;

        return aIdx - bIdx;
      });

      // Asignar los índices de orden
      return reordered.map((layer, idx) => ({
        ...layer,
        order: idx,
      }));
    });

    setOverlayData({
      ...overlayData,
      outputs: updatedOutputs,
      results: null, // Eliminar results para que use outputs
    });
  };

  // Handlers para perfil de elevación
  const handleOpenElevationProfile = () => {
    setElevationProfileOpen(true);
    setLineDrawingFinished(false);
  };

  const handleRequestLineDrawing = () => {
    setLineDrawMode(true);
    setDrawnLineCoords([]);
    setLineDrawingFinished(false);
  };

  const handleLineComplete = (coordinates) => {
    // El usuario hizo click en el cuadrado blanco - dibujo completo
    setDrawnLineCoords(coordinates);
    setLineDrawingFinished(true); // Señal para generar el perfil
  };

  const handleClearLineDrawing = () => {
    setDrawnLineCoords([]);
    setHighlightedPoint(null);
    setLineDrawMode(false);
    setLineDrawingFinished(false);
  };

  const handleHighlightPoint = (lat, lon) => {
    if (lat !== null && lon !== null) {
      setHighlightedPoint({ lat, lon });
    } else {
      setHighlightedPoint(null);
    }
  };

  const handleGenerateElevationProfile = async (coordinates) => {
    return await generateElevationProfile({ coordinates });
  };

  // Callback para indicar que el perfil fue generado
  const handleProfileGenerated = () => {
    // NO desactivamos lineDrawMode para que el dibujo permanezca visible
    setLineDrawingFinished(false); // Reset de la señal
    // NO limpiamos drawnLineCoords para que persistan en el mapa
  };

  const handleMapClickPixelStat = async (latlng) => {
    try {
      const payload = {
        filepath: activeToolFile || uploadedFiles[currentIndex],
        field: fieldsUsed?.[0] || "DBZH",
        product: overlayData?.product || "PPI",
        elevation: activeElevation,
        height: activeHeight,
        filters: filtersUsed,
        lat: latlng.lat,
        lon: latlng.lng,
        session_id: sessionId,
      };
      const resp = await generatePixelStat(payload);
      const v = resp.data?.value.toFixed(2);
      if (resp.data.masked || v == null) {
        enqueueSnackbar("Sin dato (masked / fuera de cobertura)", {
          variant: "warning",
        });
      } else {
        enqueueSnackbar(`${fieldsUsed?.[0] || "DBZH"}: ${v}`, {
          variant: "success",
        });
        setPixelStatMarker({
          lat: resp.data?.lat,
          lon: resp.data?.lon,
          value: v,
        });
      }
    } catch (e) {
      enqueueSnackbar(e?.response?.data?.detail || "Error", {
        variant: "error",
      });
    }
  };

  return (
    <div
      id="app-container"
      style={{ height: "100vh", width: "100%", position: "relative" }}
    >
      {/* Header común para ambas vistas */}
      <HeaderCard
        onUploadClick={handleFileUpload}
        logoSrc="/assets/lrsr_logo.png"
      />

      {/* Contenedor de split screen que maneja uno o dos mapas */}
      <SplitScreenContainer
        splitScreenActive={splitScreenActive}
        setSplitScreenActive={setSplitScreenActive}
        map1Props={{
          currentOverlay,
          mergedOutputs,
          opacity,
          opacityByField,
          currentIndex,
          setCurrentIndex,
          animation,
          pixelStatMode,
          setPixelStatMode,
          pixelStatMarker,
          setPixelStatMarker,
          pickPointMode,
          setPickPointMode,
          pickedPoint,
          setPickedPoint,
          areaDrawMode,
          setAreaDrawMode,
          areaPolygon,
          setAreaPolygon,
          lineDrawMode,
          setLineDrawMode,
          drawnLineCoords,
          setDrawnLineCoords,
          lineDrawingFinished,
          setLineDrawingFinished,
          highlightedPoint,
          setHighlightedPoint,
          rhiLinePreview,
          setRhiLinePreview,
          selectorOpen,
          setSelectorOpen,
          rhiOpen,
          setRhiOpen,
          areaStatsOpen,
          setAreaStatsOpen,
          elevationProfileOpen,
          setElevationProfileOpen,
          mapSelectorOpen,
          setMapSelectorOpen,
          paletteSelectorOpen,
          setPaletteSelectorOpen,
          layerManagerOpen,
          setLayerManagerOpen,
          selectedBaseMap,
          setSelectedBaseMap,
          selectedColormaps,
          setSelectedColormaps,
          initialColormaps,
          setInitialColormaps,
          onProductChosen: handleProductChosen,
          onGenerateRHI: handleGenerateRHI,
          onAreaStatsRequest: handleAreaStatsRequest,
          onPixelStatClick: handleMapClickPixelStat,
          onGenerateElevationProfile: handleGenerateElevationProfile,
          onLayerReorder: handleLayerReorder,
          mapInstance,
          setMapInstance,
          onScreenshot: handleScreenshot,
          onPrint: handlePrint,
          onFullscreen: handleFullscreen,
          isFullscreen,
          savedLayers,
          fieldsUsed,
          filtersUsed,
          activeElevation,
          activeHeight,
          activeToolFile,
          setActiveToolFile,
          radarSite,
          warnings,
          availableDownloads,
          drawnLayerRef,
          product,
          loading,
        }}
        sharedProps={{
          uploadedFiles,
          filesInfo,
          volumes,
          availableRadars,
          sessionId,
          enqueueSnackbar,
          processFile,
          generatePixelStat,
          mergeRadarFrames,
        }}
      />

      {/* UploadButton oculto - funcionalidad movida a HeaderCard */}
      <div style={{ display: "none" }}>
        <UploadButton onFilesSelected={handleFilesSelected} />
      </div>

      <Alerts
        open={alert.open}
        message={alert.message}
        severity={alert.severity}
        onClose={() => setAlert({ ...alert, open: false })}
      />
      <Loader open={loading} />
    </div>
  );
}
