import { useEffect, useState, useRef } from "react";
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Box,
  TextField,
  MenuItem,
  Typography,
  Divider,
  Paper,
  IconButton,
  Collapse,
  Autocomplete,
  Chip,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import DownloadIcon from "@mui/icons-material/Download";
import Draggable from "react-draggable";
import RadarFilterControls from "../controls/RadarFilterControls";
import ElevationChart from "../ui/ElevationChart";
import { useDownloads } from "../../hooks/useDownloads";
import { useSnackbar } from "notistack";
import { generateElevationProfile } from "../../api/backend";

const FIELD_OPTIONS = ["DBZH", "KDP", "RHOHV", "ZDR"];

function PaperComponent(props) {
  const nodeRef = useRef(null);
  return (
    <Draggable
      nodeRef={nodeRef}
      handle="#draggable-dialog-title"
      cancel={'[class*="MuiDialogContent-root"]'}
    >
      <Paper {...props} ref={nodeRef} />
    </Draggable>
  );
}

export default function PseudoRHIDialog({
  open,
  onClose,
  filepath,
  radarSite,
  fields_present = FIELD_OPTIONS,
  onRequestPickPoint,
  pickedPoint,
  onClearPickedPoint,
  onGenerate,
  onLinePreviewChange,
  onAutoClose,
  onAutoReopen,
}) {
  const [selectedFields, setSelectedFields] = useState([
    fields_present[0] || "DBZH",
  ]);
  const [startLat, setStartLat] = useState("");
  const [startLon, setStartLon] = useState("");
  const [endLat, setEndLat] = useState("");
  const [endLon, setEndLon] = useState("");
  const [loading, setLoading] = useState(false);
  const [resultImgs, setResultImgs] = useState([]);
  const [error, setError] = useState("");
  const [filters, setFilters] = useState([]);
  const [pickTarget, setPickTarget] = useState(null); // 'start' | 'end' | null
  const [autoFlowActive, setAutoFlowActive] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [maxLengthKm, setMaxLengthKm] = useState(240);
  const [maxHeightKm, setMaxHeightKm] = useState(20);
  const [expandedImage, setExpandedImage] = useState(null);
  const [elevationProfile, setElevationProfile] = useState(null);
  const [expandedElevation, setExpandedElevation] = useState(false);

  const { downloadImage, generateFilename } = useDownloads();
  const { enqueueSnackbar } = useSnackbar();

  const handleDownloadRHI = async (imageUrl, fieldName) => {
    if (!imageUrl) return;

    try {
      const filename = generateFilename(`pseudo-rhi_${fieldName}`, ".png");
      await downloadImage(imageUrl, filename);
      enqueueSnackbar("Imagen RHI descargada", { variant: "success" });
    } catch (error) {
      console.error("Error descargando RHI:", error);
      enqueueSnackbar("Error al descargar imagen", { variant: "error" });
    }
  };

  const handlePickStart = () => {
    setResultImgs([]);
    setError("");
    setPickTarget("start");
    setAutoFlowActive(true);
    onRequestPickPoint?.();
    onAutoClose?.();
  };

  const handlePickEnd = () => {
    setResultImgs([]);
    setError("");
    setPickTarget("end");
    setAutoFlowActive(true);
    onRequestPickPoint?.();
    onAutoClose?.();
  };

  const handleUseRadarOrigin = () => {
    if (radarSite) {
      setStartLat(radarSite.lat.toFixed(6));
      setStartLon(radarSite.lon.toFixed(6));
      setResultImgs([]);
      setError("");
      setElevationProfile(null);
    }
  };

  // Generar perfil de elevación cuando cambien los puntos
  useEffect(() => {
    const fetchElevationProfile = async () => {
      const hasStart = startLat !== "" && startLon !== "";
      const hasEnd = endLat !== "" && endLon !== "";

      if (!hasEnd) {
        setElevationProfile(null);
        return;
      }

      // Determinar punto de inicio (explícito o radar site)
      const start = hasStart
        ? { lat: Number(startLat), lon: Number(startLon) }
        : radarSite
        ? { lat: radarSite.lat, lon: radarSite.lon }
        : null;

      if (!start) {
        setElevationProfile(null);
        return;
      }

      const end = { lat: Number(endLat), lon: Number(endLon) };

      try {
        const response = await generateElevationProfile({
          coordinates: [start, end],
          interpolate: true,
          points_per_km: 10,
        });
        setElevationProfile(response.data);
      } catch (error) {
        console.error("Error generando perfil de elevación:", error);
        setElevationProfile(null);
      }
    };

    fetchElevationProfile();
  }, [startLat, startLon, endLat, endLon, radarSite]);

  // Map click handling: automatic chaining start -> end
  useEffect(() => {
    if (pickedPoint && pickTarget) {
      const lat = pickedPoint.lat.toFixed(6);
      const lon = pickedPoint.lon.toFixed(6);
      if (pickTarget === "start") {
        setStartLat(lat);
        setStartLon(lon);
        setPickTarget("end");
        onRequestPickPoint?.();
        return;
      }
      if (pickTarget === "end") {
        setEndLat(lat);
        setEndLon(lon);
        setPickTarget(null);
      }
    }
  }, [pickedPoint, pickTarget, onRequestPickPoint]);

  // Auto reopen when points are chosen
  useEffect(() => {
    // Reabrir cuando:
    // 1. El diálogo está cerrado
    // 2. El flujo automático está activo
    // 3. Ya no estamos en modo de selección (pickTarget === null)
    // 4. Hay al menos un punto final seleccionado
    if (
      !open &&
      autoFlowActive &&
      pickTarget === null &&
      endLat !== "" &&
      endLon !== ""
    ) {
      onAutoReopen?.();
      // Evitar re-aperturas repetidas
      setAutoFlowActive(false);
    }
  }, [open, autoFlowActive, pickTarget, endLat, endLon, onAutoReopen]);

  // Update preview line
  useEffect(() => {
    // Prioridad: usar punto de inicio explícito si existe
    // Fallback al origen del radar SOLO si no hay inicio explícito y no estamos en flujo de selección activo
    const hasExplicitStart = startLat !== "" && startLon !== "";
    const hasEnd = endLat !== "" && endLon !== "";

    let startPoint = null;
    if (hasExplicitStart) {
      startPoint = { lat: Number(startLat), lon: Number(startLon) };
    } else if (hasEnd && radarSite && !pickTarget) {
      // Si ya se eligió el fin pero no hay inicio explícito y no estamos en medio de elegir puntos,
      // usar el origen del radar como inicio implícito
      startPoint = { lat: radarSite.lat, lon: radarSite.lon };
    }

    onLinePreviewChange?.({
      start: startPoint,
      end: hasEnd ? { lat: Number(endLat), lon: Number(endLon) } : null,
    });
  }, [
    startLat,
    startLon,
    endLat,
    endLon,
    radarSite,
    pickTarget,
    onLinePreviewChange,
  ]);

  const handleGenerate = async () => {
    setResultImgs([]);
    setError("");
    if (!filepath) {
      setError("Seleccione un archivo primero");
      return;
    }
    if (selectedFields.length === 0) {
      setError("Seleccione al menos un campo");
      return;
    }
    const sLat = Number(startLat);
    const sLon = Number(startLon);
    const eLat = Number(endLat);
    const eLon = Number(endLon);
    if (!Number.isFinite(eLat) || !Number.isFinite(eLon)) {
      setError("Lat/Lon de destino inválidos");
      return;
    }
    if ((startLat === "" || startLon === "") && radarSite) {
      // usar centro del radar como inicio implícito
    } else if (!Number.isFinite(sLat) || !Number.isFinite(sLon)) {
      setError("Lat/Lon de inicio inválidos");
      return;
    }
    try {
      setLoading(true);
      const results = [];

      // Hacer una request por cada campo seleccionado
      for (const field of selectedFields) {
        try {
          const resp = await onGenerate({
            filepath,
            field,
            start_lat: startLat === "" || startLon === "" ? undefined : sLat,
            start_lon: startLat === "" || startLon === "" ? undefined : sLon,
            end_lat: eLat,
            end_lon: eLon,
            filters,
            max_length_km: Number(maxLengthKm),
            max_height_km: Number(maxHeightKm),
          });
          if (resp?.[0]?.image_url) {
            results.push({ field, image_url: resp[0].image_url });
          }
        } catch (fieldError) {
          console.error(`Error generando RHI para campo ${field}:`, fieldError);
          results.push({
            field,
            error: fieldError?.response?.data?.detail || String(fieldError),
          });
        }
      }

      setResultImgs(results);

      // Si todos los campos fallaron, mostrar error
      if (results.length > 0 && results.every((r) => r.error)) {
        setError("Error generando todos los cortes");
      }
    } catch (e) {
      setError(e?.response?.data?.detail || String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setError("");
    onClearPickedPoint?.();
    // Cancelar cualquier flujo automático pendiente
    setAutoFlowActive(false);
    setPickTarget(null);
    onClose?.();
  };

  return (
    <>
      <Dialog
        open={open}
        onClose={handleClose}
        fullWidth
        maxWidth="sm"
        hideBackdrop
        disableEnforceFocus
        disableAutoFocus
        disableRestoreFocus
        disableScrollLock
        slotProps={{
          root: { sx: { pointerEvents: "none" } },
        }}
        PaperProps={{
          sx: { pointerEvents: "auto" },
        }}
        PaperComponent={PaperComponent}
        aria-labelledby="draggable-dialog-title"
      >
        <DialogTitle id="draggable-dialog-title">
          Pseudo-RHI (corte vertical)
        </DialogTitle>
        <DialogContent id="draggable-dialog-title" dividers>
          <Box display="grid" gridTemplateColumns="1fr" gap={2} mt={2}>
            <Box display="grid" gridTemplateColumns="1fr" gap={1}>
              <Autocomplete
                multiple
                size="small"
                options={fields_present}
                value={selectedFields}
                onChange={(event, newValue) => {
                  if (newValue.length <= 3) {
                    setSelectedFields(newValue);
                  }
                }}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label="Campos (máx. 3)"
                    helperText={`${selectedFields.length}/3 campos seleccionados`}
                  />
                )}
                renderTags={(value, getTagProps) =>
                  value.map((option, index) => {
                    const { key, ...tagProps } = getTagProps({ index });
                    return (
                      <Chip
                        key={key}
                        label={option}
                        size="small"
                        {...tagProps}
                      />
                    );
                  })
                }
                disableCloseOnSelect
              />
            </Box>

            <Typography variant="subtitle2">Punto de inicio</Typography>
            <Box display="grid" gridTemplateColumns="1fr 1fr auto auto" gap={2}>
              <TextField
                size="small"
                label="Latitud inicio"
                value={startLat}
                onChange={(e) => setStartLat(e.target.value)}
                disabled={pickTarget === "end"}
              />
              <TextField
                size="small"
                label="Longitud inicio"
                value={startLon}
                onChange={(e) => setStartLon(e.target.value)}
                disabled={pickTarget === "end"}
              />
              <Button
                variant="outlined"
                onClick={handlePickStart}
                disabled={pickTarget === "end"}
              >
                Elegir en mapa
              </Button>
              <Button
                variant="contained"
                onClick={handleUseRadarOrigin}
                disabled={pickTarget === "end" || !radarSite}
                size="small"
              >
                Usar origen
              </Button>
            </Box>
            {pickTarget === "end" && startLat !== "" && startLon !== "" && (
              <Typography variant="caption" sx={{ opacity: 0.7 }}>
                Seleccioná ahora el punto de fin en el mapa…
              </Typography>
            )}

            <Typography variant="subtitle2">Punto de fin</Typography>
            <Box display="grid" gridTemplateColumns="1fr 1fr auto" gap={2}>
              <TextField
                size="small"
                label="Latitud fin"
                value={endLat}
                onChange={(e) => setEndLat(e.target.value)}
                disabled={pickTarget === "start"}
              />
              <TextField
                size="small"
                label="Longitud fin"
                value={endLon}
                onChange={(e) => setEndLon(e.target.value)}
                disabled={pickTarget === "start"}
              />
              <Button
                variant="outlined"
                onClick={handlePickEnd}
                disabled={pickTarget === "start"}
              >
                Elegir en mapa
              </Button>
            </Box>
          </Box>

          {radarSite && (
            <Typography variant="caption" sx={{ opacity: 0.7 }}>
              Centro del radar: lat{" "}
              {radarSite.lat.toFixed?.(4) ?? radarSite.lat}, lon{" "}
              {radarSite.lon.toFixed?.(4) ?? radarSite.lon}
            </Typography>
          )}

          <Box mt={3}>
            <Box display="flex" alignItems="center" gap={1}>
              <IconButton
                size="small"
                onClick={() => setShowFilters((v) => !v)}
                aria-label={showFilters ? "Ocultar filtros" : "Mostrar filtros"}
              >
                {showFilters ? <ExpandLessIcon /> : <ExpandMoreIcon />}
              </IconButton>
              <Typography variant="subtitle2" sx={{ userSelect: "none" }}>
                Filtros{" "}
                {selectedFields.length > 1 && "(se aplican a todos los campos)"}
              </Typography>
            </Box>
            <Collapse in={showFilters} timeout="auto" unmountOnExit>
              <Box mt={1}>
                <RadarFilterControls
                  selectedField={selectedFields[0]}
                  onFiltersChange={setFilters}
                  showVariableFilterDefault={true}
                />
                <Box
                  mt={2}
                  display="grid"
                  gridTemplateColumns="1fr 1fr"
                  gap={2}
                >
                  <TextField
                    size="small"
                    label="Distancia máx (km)"
                    type="number"
                    value={maxLengthKm}
                    onChange={(e) => {
                      const v = Number(e.target.value);
                      if (!Number.isFinite(v)) return;
                      setMaxLengthKm(Math.min(500, Math.max(1, v)));
                    }}
                    helperText="Rango horizontal del corte"
                  />
                  <TextField
                    size="small"
                    label="Altura máx (km)"
                    type="number"
                    value={maxHeightKm}
                    onChange={(e) => {
                      const v = Number(e.target.value);
                      if (!Number.isFinite(v)) return;
                      setMaxHeightKm(Math.min(30, Math.max(0.5, v)));
                    }}
                    helperText="Altura vertical del corte"
                  />
                </Box>
              </Box>
            </Collapse>
          </Box>
          {resultImgs.length > 0 && (
            <>
              <Divider sx={{ my: 2 }} />
              <Box>
                <Typography variant="subtitle2" color="text.secondary" mb={2}>
                  Resultados de los cortes verticales
                </Typography>
                {resultImgs.map((result, idx) => (
                  <Box key={idx} mb={3}>
                    <Box
                      display="flex"
                      justifyContent="space-between"
                      alignItems="center"
                      mb={1}
                    >
                      <Typography variant="body2" fontWeight="medium">
                        Campo: {result.field}
                      </Typography>
                      {result.image_url && (
                        <Button
                          size="small"
                          startIcon={<DownloadIcon />}
                          onClick={() =>
                            handleDownloadRHI(result.image_url, result.field)
                          }
                          variant="outlined"
                        >
                          Descargar
                        </Button>
                      )}
                    </Box>
                    {result.image_url ? (
                      <Box display="flex" justifyContent="center">
                        <img
                          src={result.image_url}
                          alt={`pseudo-rhi-${result.field}`}
                          style={{
                            maxWidth: "100%",
                            borderRadius: 8,
                            cursor: "pointer",
                            transition: "opacity 0.2s",
                          }}
                          onMouseOver={(e) => (e.target.style.opacity = "0.8")}
                          onMouseOut={(e) => (e.target.style.opacity = "1")}
                          onClick={() => setExpandedImage(result)}
                        />
                      </Box>
                    ) : result.error ? (
                      <Typography color="error" variant="body2">
                        Error: {result.error}
                      </Typography>
                    ) : null}
                  </Box>
                ))}
              </Box>

              {/* Perfil de elevación del terreno */}
              {elevationProfile?.profile &&
                elevationProfile.profile.length > 0 && (
                  <>
                    <Divider sx={{ my: 2 }} />
                    <Box>
                      <Typography
                        variant="subtitle2"
                        color="text.secondary"
                        mb={2}
                      >
                        Perfil de elevación del terreno
                      </Typography>
                      <ElevationChart
                        profileData={elevationProfile.profile}
                        height={200}
                        clickable={true}
                        onClick={() => setExpandedElevation(true)}
                      />
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{ mt: 1, display: "block" }}
                      >
                        Haz clic en el gráfico para verlo más grande
                      </Typography>
                    </Box>
                  </>
                )}
            </>
          )}

          {error && (
            <Typography color="error" mt={2}>
              {error}
            </Typography>
          )}
        </DialogContent>

        <DialogActions>
          <Button onClick={handleClose} color="secondary">
            Cerrar
          </Button>
          <Button
            onClick={handleGenerate}
            variant="contained"
            disabled={loading}
          >
            {loading ? "Generando..." : "Generar corte"}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Modal para ver imagen expandida */}
      <Dialog
        open={!!expandedImage}
        onClose={() => setExpandedImage(null)}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle>Pseudo-RHI - Campo: {expandedImage?.field}</DialogTitle>
        <DialogContent>
          <Box
            display="flex"
            justifyContent="center"
            alignItems="center"
            sx={{ minHeight: "60vh" }}
          >
            {expandedImage?.image_url && (
              <img
                src={expandedImage.image_url}
                alt={`pseudo-rhi-${expandedImage.field}`}
                style={{
                  maxWidth: "100%",
                  maxHeight: "80vh",
                  objectFit: "contain",
                }}
              />
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          {expandedImage?.image_url && (
            <Button
              startIcon={<DownloadIcon />}
              onClick={() =>
                handleDownloadRHI(expandedImage.image_url, expandedImage.field)
              }
              variant="outlined"
            >
              Descargar
            </Button>
          )}
          <Button onClick={() => setExpandedImage(null)} variant="contained">
            Cerrar
          </Button>
        </DialogActions>
      </Dialog>

      {/* Modal para ver gráfico de elevación expandido */}
      <Dialog
        open={expandedElevation}
        onClose={() => setExpandedElevation(false)}
        maxWidth="xl"
        fullWidth
      >
        <DialogTitle>Perfil de elevación del terreno</DialogTitle>
        <DialogContent>
          <Box sx={{ minHeight: "60vh", py: 2 }}>
            {elevationProfile?.profile && (
              <ElevationChart
                profileData={elevationProfile.profile}
                height={500}
                clickable={false}
              />
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => setExpandedElevation(false)}
            variant="contained"
          >
            Cerrar
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
