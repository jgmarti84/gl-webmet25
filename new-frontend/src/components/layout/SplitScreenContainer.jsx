import { useState, useRef, useEffect } from "react";
import { Box } from "@mui/material";
import MapPanel from "./MapPanel";
import { useSplitScreenSync } from "../../hooks/useSplitScreenSync";

/**
 * SplitScreenContainer - Gestiona la visualización de uno o dos mapas
 * y su sincronización cuando están en modo lock
 */
export default function SplitScreenContainer({
  // Props del mapa principal (izquierdo)
  map1Props,

  // Props compartidas entre ambos mapas
  sharedProps,

  // Estados globales
  splitScreenActive,
  setSplitScreenActive,
}) {
  // Estados independientes para el segundo mapa
  const [map2Instance, setMap2Instance] = useState(null);
  const [locked, setLocked] = useState(false);

  // Estados del segundo mapa (cuando está en split)
  const [overlayData2, setOverlayData2] = useState(null);
  const [opacity2, setOpacity2] = useState([0.95]);
  const [opacityByField2, setOpacityByField2] = useState({});
  const [currentIndex2, setCurrentIndex2] = useState(0);
  const [pixelStatMode2, setPixelStatMode2] = useState(false);
  const [pixelStatMarker2, setPixelStatMarker2] = useState(null);
  const [pickPointMode2, setPickPointMode2] = useState(false);
  const [pickedPoint2, setPickedPoint2] = useState(null);
  const [areaDrawMode2, setAreaDrawMode2] = useState(false);
  const [areaPolygon2, setAreaPolygon2] = useState(null);
  const [lineDrawMode2, setLineDrawMode2] = useState(false);
  const [drawnLineCoords2, setDrawnLineCoords2] = useState([]);
  const [lineDrawingFinished2, setLineDrawingFinished2] = useState(false);
  const [highlightedPoint2, setHighlightedPoint2] = useState(null);
  const [rhiLinePreview2, setRhiLinePreview2] = useState({
    start: null,
    end: null,
  });

  // Diálogos del segundo mapa
  const [selectorOpen2, setSelectorOpen2] = useState(false);
  const [rhiOpen2, setRhiOpen2] = useState(false);
  const [areaStatsOpen2, setAreaStatsOpen2] = useState(false);
  const [elevationProfileOpen2, setElevationProfileOpen2] = useState(false);
  const [mapSelectorOpen2, setMapSelectorOpen2] = useState(false);
  const [paletteSelectorOpen2, setPaletteSelectorOpen2] = useState(false);
  const [layerManagerOpen2, setLayerManagerOpen2] = useState(false);

  // Estados compartibles entre mapas (pero independientes inicialmente)
  const [selectedBaseMap2, setSelectedBaseMap2] = useState(
    map1Props.selectedBaseMap
  );
  const [selectedColormaps2, setSelectedColormaps2] = useState({});
  const [initialColormaps2, setInitialColormaps2] = useState({});
  const [fieldsUsed2, setFieldsUsed2] = useState([]);
  const [savedLayers2, setSavedLayers2] = useState([]);
  const [filtersUsed2, setFiltersUsed2] = useState([]);
  const [activeElevation2, setActiveElevation2] = useState(null);
  const [activeHeight2, setActiveHeight2] = useState(null);
  const [activeToolFile2, setActiveToolFile2] = useState(null);
  const [warnings2, setWarnings2] = useState([]);
  const [product2, setProduct2] = useState("PPI");
  const [loading2, setLoading2] = useState(false);

  const drawnLayerRef2 = useRef(null);

  // Sincronizar mapas cuando están en lock
  useSplitScreenSync(
    map1Props.mapInstance,
    map2Instance,
    locked,
    map1Props.currentIndex,
    currentIndex2,
    setCurrentIndex2
  );

  // Recalcular tamaño del mapa principal cuando se activa/desactiva split
  useEffect(() => {
    if (map1Props.mapInstance) {
      // Usar setTimeout para asegurar que el DOM se actualizó antes de recalcular
      const timer = setTimeout(() => {
        try {
          map1Props.mapInstance.invalidateSize({ animate: false });
        } catch (error) {
          console.error("Error al recalcular tamaño del mapa:", error);
        }
      }, 100);

      return () => clearTimeout(timer);
    }
  }, [splitScreenActive, map1Props.mapInstance]);

  // Sincronizar mapa base cuando está locked
  const handleSelectBaseMap2 = (map) => {
    setSelectedBaseMap2(map);
    if (locked) {
      map1Props.setSelectedBaseMap(map);
    }
  };

  // También sincronizar desde mapa 1 hacia mapa 2 cuando se bloquea
  const handleSelectBaseMap1 = (map) => {
    map1Props.setSelectedBaseMap(map);
    if (locked) {
      setSelectedBaseMap2(map);
    }
  };

  const handleToggleSplit = () => {
    setSplitScreenActive((prev) => {
      const next = !prev;
      if (!next) {
        // Al cerrar split, desbloquear
        setLocked(false);
        // Limpiar estados del mapa 2
        setOverlayData2(null);
        setCurrentIndex2(0);
      }
      return next;
    });
  };

  const handleToggleLock = () => {
    setLocked((prev) => {
      const next = !prev;
      if (next) {
        // Al activar lock, sincronizar mapa base
        setSelectedBaseMap2(map1Props.selectedBaseMap);
      }
      return next;
    });
  };

  // Handlers para el mapa 2
  const handleProductChosen2 = async (data) => {
    // Similar a handleProductChosen del mapa 1, pero actualiza estados del mapa 2
    setLoading2(true);
    try {
      // Filtrar solo los layers habilitados y extraer los nombres (como strings)
      const enabledLayerObjs = data.layers.filter((l) => l.enabled);
      const enabledLayers = enabledLayerObjs.map((l) => l.label);

      // Build field-based opacity map
      const opacityMap = Object.fromEntries(
        enabledLayerObjs.map((l) => [
          String(l.label || l.field).toUpperCase(),
          Number(l.opacity ?? 1),
        ])
      );
      const opacities = enabledLayerObjs.map((l) => l.opacity);

      setOpacity2(opacities);
      setOpacityByField2(opacityMap);

      const processResp = await sharedProps.processFile({
        files: sharedProps.uploadedFiles, // Usar los archivos compartidos
        layers: enabledLayers, // Array de strings con los nombres de los campos
        product: data.product,
        height: data.height,
        elevation: data.elevation,
        filters: data.filters,
        selectedVolumes: data.selectedVolumes,
        selectedRadars: data.selectedRadars,
        colormap_overrides: selectedColormaps2,
        session_id: sharedProps.sessionId,
      });

      if (processResp.data) {
        // Merge frames similar al mapa 1
        const mergedOutputs = sharedProps.mergeRadarFrames(
          processResp.data.results || []
        );
        setOverlayData2(mergedOutputs);
        setWarnings2(processResp.data.warnings || []);
        setCurrentIndex2(0);
        setFieldsUsed2(enabledLayers); // Array de strings con nombres de campos
        setSavedLayers2(data.layers);
        setFiltersUsed2(data.filters || []);
        setActiveElevation2(data.elevation);
        setActiveHeight2(data.height);
        setInitialColormaps2({ ...selectedColormaps2 });
        setProduct2(data.product || "PPI");
      }
    } catch (error) {
      console.error("Error al procesar producto en mapa 2:", error);
      sharedProps.enqueueSnackbar("Error al procesar producto", {
        variant: "error",
      });
    } finally {
      setLoading2(false);
    }
  };

  const handlePixelStatClick2 = async (latlng) => {
    // Similar al mapa 1
    try {
      const payload = {
        filepath: activeToolFile2 || sharedProps.uploadedFiles[currentIndex2],
        field: fieldsUsed2?.[0] || "DBZH",
        product: product2 || "PPI",
        elevation: activeElevation2,
        height: activeHeight2,
        filters: filtersUsed2,
        lat: latlng.lat,
        lon: latlng.lng,
        session_id: sharedProps.sessionId,
      };
      const resp = await sharedProps.generatePixelStat(payload);
      const v = resp.data?.value.toFixed(2);
      if (resp.data.masked || v == null) {
        sharedProps.enqueueSnackbar("Sin dato (masked / fuera de cobertura)", {
          variant: "warning",
        });
      } else {
        sharedProps.enqueueSnackbar(`${fieldsUsed2?.[0] || "DBZH"}: ${v}`, {
          variant: "success",
        });
        setPixelStatMarker2({
          lat: resp.data?.lat,
          lon: resp.data?.lon,
          value: v,
        });
      }
    } catch (e) {
      sharedProps.enqueueSnackbar(e?.response?.data?.detail || "Error", {
        variant: "error",
      });
    }
  };

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "row",
        height: "100vh",
        width: "100%",
        position: "absolute",
        top: 0,
        left: 0,
      }}
    >
      {/* Mapa principal (izquierdo) */}
      <Box
        sx={{
          flex: splitScreenActive ? 1 : 1,
          height: "100%",
          position: "relative",
        }}
      >
        <MapPanel
          panelId="main"
          overlayData={map1Props.currentOverlay}
          mergedOutputs={map1Props.mergedOutputs}
          opacity={map1Props.opacity}
          opacityByField={map1Props.opacityByField}
          currentIndex={map1Props.currentIndex}
          setCurrentIndex={map1Props.setCurrentIndex}
          animation={map1Props.animation}
          pixelStatMode={map1Props.pixelStatMode}
          setPixelStatMode={map1Props.setPixelStatMode}
          pixelStatMarker={map1Props.pixelStatMarker}
          setPixelStatMarker={map1Props.setPixelStatMarker}
          pickPointMode={map1Props.pickPointMode}
          setPickPointMode={map1Props.setPickPointMode}
          pickedPoint={map1Props.pickedPoint}
          setPickedPoint={map1Props.setPickedPoint}
          areaDrawMode={map1Props.areaDrawMode}
          setAreaDrawMode={map1Props.setAreaDrawMode}
          areaPolygon={map1Props.areaPolygon}
          setAreaPolygon={map1Props.setAreaPolygon}
          lineDrawMode={map1Props.lineDrawMode}
          setLineDrawMode={map1Props.setLineDrawMode}
          drawnLineCoords={map1Props.drawnLineCoords}
          setDrawnLineCoords={map1Props.setDrawnLineCoords}
          lineDrawingFinished={map1Props.lineDrawingFinished}
          setLineDrawingFinished={map1Props.setLineDrawingFinished}
          highlightedPoint={map1Props.highlightedPoint}
          setHighlightedPoint={map1Props.setHighlightedPoint}
          rhiLinePreview={map1Props.rhiLinePreview}
          setRhiLinePreview={map1Props.setRhiLinePreview}
          selectorOpen={map1Props.selectorOpen}
          setSelectorOpen={map1Props.setSelectorOpen}
          rhiOpen={map1Props.rhiOpen}
          setRhiOpen={map1Props.setRhiOpen}
          areaStatsOpen={map1Props.areaStatsOpen}
          setAreaStatsOpen={map1Props.setAreaStatsOpen}
          elevationProfileOpen={map1Props.elevationProfileOpen}
          setElevationProfileOpen={map1Props.setElevationProfileOpen}
          mapSelectorOpen={map1Props.mapSelectorOpen}
          setMapSelectorOpen={map1Props.setMapSelectorOpen}
          paletteSelectorOpen={map1Props.paletteSelectorOpen}
          setPaletteSelectorOpen={map1Props.setPaletteSelectorOpen}
          layerManagerOpen={map1Props.layerManagerOpen}
          setLayerManagerOpen={map1Props.setLayerManagerOpen}
          selectedBaseMap={map1Props.selectedBaseMap}
          setSelectedBaseMap={handleSelectBaseMap1}
          selectedColormaps={map1Props.selectedColormaps}
          setSelectedColormaps={map1Props.setSelectedColormaps}
          initialColormaps={map1Props.initialColormaps}
          setInitialColormaps={map1Props.setInitialColormaps}
          onProductChosen={map1Props.onProductChosen}
          onGenerateRHI={map1Props.onGenerateRHI}
          onAreaStatsRequest={map1Props.onAreaStatsRequest}
          onPixelStatClick={map1Props.onPixelStatClick}
          onGenerateElevationProfile={map1Props.onGenerateElevationProfile}
          onLayerReorder={map1Props.onLayerReorder}
          onMapReady={map1Props.setMapInstance}
          onScreenshot={() =>
            map1Props.onScreenshot(map1Props.mapInstance, "map-container-main")
          }
          onPrint={map1Props.onPrint}
          onFullscreen={map1Props.onFullscreen}
          isFullscreen={map1Props.isFullscreen}
          uploadedFiles={sharedProps.uploadedFiles}
          filesInfo={sharedProps.filesInfo}
          volumes={sharedProps.volumes}
          availableRadars={sharedProps.availableRadars}
          savedLayers={map1Props.savedLayers}
          fieldsUsed={map1Props.fieldsUsed}
          filtersUsed={map1Props.filtersUsed}
          activeElevation={map1Props.activeElevation}
          activeHeight={map1Props.activeHeight}
          activeToolFile={map1Props.activeToolFile}
          setActiveToolFile={map1Props.setActiveToolFile}
          radarSite={map1Props.radarSite}
          warnings={map1Props.warnings}
          availableDownloads={map1Props.availableDownloads}
          drawnLayerRef={map1Props.drawnLayerRef}
          product={map1Props.product}
          isSplitScreen={splitScreenActive}
          showSplitButton={true}
          showLockButton={splitScreenActive}
          locked={locked}
          onToggleSplit={handleToggleSplit}
          onToggleLock={handleToggleLock}
          loading={map1Props.loading || false}
        />
      </Box>

      {/* Mapa secundario (derecho) - Solo visible en split screen */}
      {splitScreenActive && (
        <Box
          sx={{
            flex: 1,
            height: "100%",
            position: "relative",
            borderLeft: "2px solid rgba(0, 0, 0, 0.1)",
          }}
        >
          <MapPanel
            panelId="secondary"
            overlayData={
              Array.isArray(overlayData2) && overlayData2.length > 0
                ? overlayData2[currentIndex2]
                : null
            }
            mergedOutputs={overlayData2}
            opacity={opacity2}
            opacityByField={opacityByField2}
            currentIndex={currentIndex2}
            setCurrentIndex={setCurrentIndex2}
            animation={Array.isArray(overlayData2) && overlayData2.length > 1}
            pixelStatMode={pixelStatMode2}
            setPixelStatMode={setPixelStatMode2}
            pixelStatMarker={pixelStatMarker2}
            setPixelStatMarker={setPixelStatMarker2}
            pickPointMode={pickPointMode2}
            setPickPointMode={setPickPointMode2}
            pickedPoint={pickedPoint2}
            setPickedPoint={setPickedPoint2}
            areaDrawMode={areaDrawMode2}
            setAreaDrawMode={setAreaDrawMode2}
            areaPolygon={areaPolygon2}
            setAreaPolygon={setAreaPolygon2}
            lineDrawMode={lineDrawMode2}
            setLineDrawMode={setLineDrawMode2}
            drawnLineCoords={drawnLineCoords2}
            setDrawnLineCoords={setDrawnLineCoords2}
            lineDrawingFinished={lineDrawingFinished2}
            setLineDrawingFinished={setLineDrawingFinished2}
            highlightedPoint={highlightedPoint2}
            setHighlightedPoint={setHighlightedPoint2}
            rhiLinePreview={rhiLinePreview2}
            setRhiLinePreview={setRhiLinePreview2}
            selectorOpen={selectorOpen2}
            setSelectorOpen={setSelectorOpen2}
            rhiOpen={rhiOpen2}
            setRhiOpen={setRhiOpen2}
            areaStatsOpen={areaStatsOpen2}
            setAreaStatsOpen={setAreaStatsOpen2}
            elevationProfileOpen={elevationProfileOpen2}
            setElevationProfileOpen={setElevationProfileOpen2}
            mapSelectorOpen={mapSelectorOpen2}
            setMapSelectorOpen={setMapSelectorOpen2}
            paletteSelectorOpen={paletteSelectorOpen2}
            setPaletteSelectorOpen={setPaletteSelectorOpen2}
            layerManagerOpen={layerManagerOpen2}
            setLayerManagerOpen={setLayerManagerOpen2}
            selectedBaseMap={selectedBaseMap2}
            setSelectedBaseMap={handleSelectBaseMap2}
            selectedColormaps={selectedColormaps2}
            setSelectedColormaps={setSelectedColormaps2}
            initialColormaps={initialColormaps2}
            setInitialColormaps={setInitialColormaps2}
            onProductChosen={handleProductChosen2}
            onGenerateRHI={map1Props.onGenerateRHI}
            onAreaStatsRequest={map1Props.onAreaStatsRequest}
            onPixelStatClick={handlePixelStatClick2}
            onGenerateElevationProfile={map1Props.onGenerateElevationProfile}
            onLayerReorder={(layers) => {
              // Aplicar reorden en mapa 2
              const updatedOverlay = [...(overlayData2[currentIndex2] || [])];
              layers.forEach((layer, idx) => {
                const foundIdx = updatedOverlay.findIndex(
                  (l) => l.field === layer.field
                );
                if (foundIdx !== -1) {
                  updatedOverlay[foundIdx] = {
                    ...updatedOverlay[foundIdx],
                    order: idx,
                  };
                }
              });
              const newData = [...overlayData2];
              newData[currentIndex2] = updatedOverlay;
              setOverlayData2(newData);
            }}
            onMapReady={setMap2Instance}
            onScreenshot={() =>
              map1Props.onScreenshot(map2Instance, "map-container-secondary")
            }
            onPrint={map1Props.onPrint}
            onFullscreen={map1Props.onFullscreen}
            isFullscreen={map1Props.isFullscreen}
            uploadedFiles={sharedProps.uploadedFiles}
            filesInfo={sharedProps.filesInfo}
            volumes={sharedProps.volumes}
            availableRadars={sharedProps.availableRadars}
            savedLayers={savedLayers2}
            fieldsUsed={fieldsUsed2}
            filtersUsed={filtersUsed2}
            activeElevation={activeElevation2}
            activeHeight={activeHeight2}
            activeToolFile={activeToolFile2}
            setActiveToolFile={setActiveToolFile2}
            radarSite={map1Props.radarSite}
            warnings={warnings2}
            availableDownloads={{}}
            drawnLayerRef={drawnLayerRef2}
            product={product2}
            isSplitScreen={splitScreenActive}
            showSplitButton={false}
            showLockButton={false}
            locked={locked}
            onToggleSplit={handleToggleSplit}
            onToggleLock={handleToggleLock}
            loading={loading2}
          />
        </Box>
      )}
    </Box>
  );
}
