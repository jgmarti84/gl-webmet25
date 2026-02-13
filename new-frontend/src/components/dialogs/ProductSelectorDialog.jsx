import { useEffect, useMemo, useState } from "react";
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  FormControl,
  RadioGroup,
  FormControlLabel,
  Radio,
  Typography,
  Box,
  Slider,
  TextField,
  InputAdornment,
  Checkbox,
  Divider,
  IconButton,
  Collapse,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import LayerControlList from "../controls/LayerControlList";

const MARKS_01 = [
  { value: 0, label: "0" },
  { value: 0.25, label: "0.25" },
  { value: 0.5, label: "0.5" },
  { value: 0.75, label: "0.75" },
  { value: 1, label: "1" },
];

const FIELD_LIMITS = {
  DBZH: { min: -30, max: 70 },
  DBZV: { min: -30, max: 70 },
  DBZHF: { min: -30, max: 70 },
  ZDR: { min: -5, max: 10.5 },
  RHOHV: { min: 0.3, max: 1.0 },
  KDP: { min: 0, max: 8 },
  VRAD: { min: -35, max: 35 },
  WRAD: { min: 0, max: 10 },
  PHIDP: { min: -180, max: 180 },
};

// Si llega un alias raro del archivo, lo “canonizamos”
const CANON = {
  dbzh: "DBZH",
  zdr: "ZDR",
  rhohv: "RHOHV",
  kdp: "KDP",
  dbzv: "DBZV",
  vrad: "VRAD",
  wrad: "WRAD",
  phidp: "PHIDP",
};

function canonize(name = "") {
  const k = String(name).toLowerCase();
  return CANON[k] || name.toUpperCase();
}

// Crear capas a partir de fields_present
function deriveLayersFromFields(fields_present) {
  const uniq = Array.from(new Set((fields_present || []).map(canonize)));
  // Orden sugerido: DBZH primero si existe
  const order = [
    "DBZH",
    "DBZV",
    "KDP",
    "RHOHV",
    "ZDR",
    "VRAD",
    "WRAD",
    "PHIDP",
  ];
  const sorted = uniq.sort((a, b) => {
    const ia = order.indexOf(a);
    const ib = order.indexOf(b);
    return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib);
  });
  return sorted.map((f, i) => ({
    id: f.toLowerCase(),
    label: f,
    field: f,
    enabled: i === 0,
    opacity: 1,
  }));
}

export default function ProductSelectorDialog({
  open,
  fields_present = ["DBZH"],
  elevations = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
  volumes = [],
  radars = [],
  onClose,
  onConfirm,
  initialProduct = "ppi",
  initialCappiHeight = 2000,
  initialElevation = 0,
  initialLayers = [],
  initialFilters = {
    rhohv: { enabled: false, min: 0.92, max: 1.0 },
    other: { enabled: false, min: 0, max: 1.0 },
  },
}) {
  const MAX_RADARS = 3;
  const derivedLayers = useMemo(
    () =>
      initialLayers.length > 0
        ? initialLayers
        : deriveLayersFromFields(fields_present),
    [fields_present, initialLayers]
  );

  const [layers, setLayers] = useState(derivedLayers);
  const [product, setProduct] = useState(initialProduct);
  const [height, setHeight] = useState(initialCappiHeight);
  const [selectedVolumes, setSelectedVolumes] = useState(volumes);
  const [selectedRadars, setSelectedRadars] = useState(radars);

  // Elevación: trabajemos con índices de elevación
  const initialElevationIndex = useMemo(() => {
    const N = Array.isArray(elevations) ? elevations.length : 0;
    const idx = Number.isInteger(initialElevation) ? initialElevation : 0;
    return Math.max(0, Math.min(Math.max(N - 1, 0), idx));
  }, [elevations, initialElevation]);

  const [elevationIdx, setElevationIdx] = useState(initialElevationIndex);
  const [filters, setFilters] = useState(structuredClone(initialFilters));
  const [showFilters, setShowFilters] = useState(false);

  // Actualizar capas preservando el orden del usuario cuando cambian los campos disponibles
  useEffect(() => {
    if (layers.length === 0 || !layers.some((l) => l.enabled)) {
      setLayers(derivedLayers);
      return;
    }

    // Si derivedLayers cambió, sincronizar el orden
    // Comparar si el orden de los campos habilitados cambió
    const currentEnabledFields = layers
      .filter((l) => l.enabled)
      .map((l) => l.field);
    const derivedEnabledFields = derivedLayers
      .filter((l) => l.enabled)
      .map((l) => l.field);

    // Si el orden cambió, reordenar manteniendo estados enabled/disabled
    const orderChanged =
      currentEnabledFields.length === derivedEnabledFields.length &&
      currentEnabledFields.some(
        (field, idx) => field !== derivedEnabledFields[idx]
      );

    if (orderChanged) {
      // Reordenar layers según el orden en derivedLayers, manteniendo enabled/disabled
      const reordered = [];

      // Primero los campos en el orden de derivedLayers
      derivedLayers.forEach((dl) => {
        const existing = layers.find((l) => l.field === dl.field);
        if (existing) {
          reordered.push(existing);
        } else {
          reordered.push(dl);
        }
      });

      // Luego los campos que están en layers pero no en derivedLayers
      layers.forEach((l) => {
        if (!derivedLayers.find((dl) => dl.field === l.field)) {
          reordered.push(l);
        }
      });

      setLayers(reordered);
      return;
    }

    // Si hay nuevos campos en derivedLayers que no están en layers actuales, agregarlos al final
    const currentFields = new Set(layers.map((l) => l.field));
    const newLayers = derivedLayers.filter(
      (dl) => !currentFields.has(dl.field)
    );

    if (newLayers.length > 0) {
      // Agregar nuevos campos al final, manteniendo el orden existente
      setLayers((prev) => [...prev, ...newLayers]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [derivedLayers]);

  useEffect(() => {
    setElevationIdx(initialElevationIndex);
  }, [initialElevationIndex]);

  useEffect(() => {
    setSelectedVolumes(volumes);
  }, [volumes]);

  // Reset height to default when product changes from/to CAPPI
  useEffect(() => {
    if (product !== 'cappi') {
      setHeight(initialCappiHeight);
    }
  }, [product, initialCappiHeight]);

  useEffect(() => {
    // Cap default selection to MAX_RADARS to avoid overloading UI/backend
    setSelectedRadars(Array.isArray(radars) ? radars.slice(0, MAX_RADARS) : []);
  }, [radars]);

  // Variable activa (usamos para los filtros)
  const activeField = (
    layers.find((l) => l.enabled)?.field ||
    layers.find((l) => l.enabled)?.label ||
    "DBZH"
  ).toUpperCase();
  const limits = FIELD_LIMITS[activeField] || { min: 0, max: 1 };

  const [activeRange, setActiveRange] = useState([limits.min, limits.max]);

  useEffect(() => {
    const lim = FIELD_LIMITS[activeField] || { min: 0, max: 1 };
    // Si el filtro other está habilitado, mantener sus valores, sino resetear a los límites del campo
    if (!filters.other?.enabled) {
      setActiveRange([lim.min, lim.max]);
    }
  }, [activeField, filters.other?.enabled]);

  const isCAPPI = product === "cappi";
  const isPPI = product === "ppi";

  const setRhohv = (patch) =>
    setFilters((f) => ({ ...f, rhohv: { ...f.rhohv, ...patch } }));
  const setOther = (patch) =>
    setFilters((f) => ({ ...f, other: { ...f.other, ...patch } }));

  const clamp01 = (v) => Math.max(0, Math.min(1, Number(v)));

  const handleAccept = () => {
    const filtersOut = [];

    // Filtro de rango de variable activa (solo si está habilitado)
    if (filters.other?.enabled) {
      const [amin, amax] = activeRange;
      filtersOut.push({
        field: activeField,
        type: "range",
        min: amin,
        max: amax,
        enabled: true,
      });
    }

    // Filtro RHOHV
    if (filters.rhohv?.enabled) {
      let min = clamp01(filters.rhohv.min ?? 0);
      let max = clamp01(filters.rhohv.max ?? 1);
      if (min > max) [min, max] = [max, min];
      filtersOut.push({
        field: "RHOHV",
        type: "range",
        min,
        max,
        enabled: true,
      });
    }

    // Para COLMAX, forzar DBZH como única capa
    const finalLayers = product === "colmax"
      ? [{ id: "dbzh", label: "DBZH", field: "DBZH", enabled: true, opacity: 1 }]
      : layers;

    onConfirm({
      layers: finalLayers,
      product,
      height: isCAPPI ? height : undefined,
      elevation: isPPI ? elevationIdx : undefined,
      filters: filtersOut,
      selectedVolumes,
      selectedRadars,
    });
    onClose();
  };

  const handleClose = () => {
    setLayers(derivedLayers);
    setProduct(initialProduct);
    setHeight(initialCappiHeight);
    setElevationIdx(initialElevationIndex);
    setFilters(structuredClone(initialFilters));
    setSelectedVolumes(volumes);
    setSelectedRadars(radars);
    onClose();
  };

  // Marks del slider de elevación
  const elevMarks = useMemo(() => {
    const N = Array.isArray(elevations) ? elevations.length : 0;
    const step = N > 9 ? Math.ceil(N / 9) : 1; // máx 9 marcas visibles
    return Array.from({ length: N }, (_, i) =>
      i % step === 0 ? { value: i, label: String(i) } : null
    ).filter(Boolean);
  }, [elevations]);

  const maxIdx = Math.max(0, (elevations?.length || 1) - 1);

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Opciones de Visualización</DialogTitle>

      <DialogContent dividers>
        {/* Grid layout: Vista a la izquierda, Volúmenes y Radares a la derecha */}
        <Box display="grid" gridTemplateColumns="1fr 1fr" gap={3}>
          {/* Columna izquierda: Seleccionar Vista */}
          <Box>
            <Typography variant="subtitle1" gutterBottom>
              Seleccionar Vista
            </Typography>
            <FormControl component="fieldset" fullWidth>
              <RadioGroup
                value={product}
                onChange={(e) => setProduct(e.target.value)}
              >
                <FormControlLabel value="ppi" control={<Radio />} label="PPI" />
                <FormControlLabel
                  value="colmax"
                  control={<Radio />}
                  label="COLMAX"
                />
                <FormControlLabel value="cappi" control={<Radio />} label="CAPPI" />
              </RadioGroup>
            </FormControl>
          </Box>

          {/* Columna derecha: Volúmenes y Radares apilados */}
          <Box display="flex" flexDirection="column" gap={2}>
            {/* Selección de volúmenes */}
            {Array.isArray(volumes) && volumes.length > 0 && (
              <Box>
                <Typography variant="subtitle1" mb={2} gutterBottom>
                  Seleccionar volúmenes
                </Typography>
                <Box display="flex" flexWrap="wrap" gap={1}>
                  {volumes.map((vol, idx) => {
                    const isSelected = selectedVolumes.includes(vol);
                    return (
                      <Button
                        key={vol}
                        variant={isSelected ? "contained" : "outlined"}
                        onClick={() => {
                          setSelectedVolumes((prev) =>
                            prev.includes(vol)
                              ? prev.filter((v) => v !== vol)
                              : [...prev, vol]
                          );
                        }}
                        sx={{
                          borderRadius: 999,
                          backgroundColor: isSelected ? "#888" : "#eee",
                          color: isSelected ? "#fff" : "#333",
                          fontWeight: 500,
                          textTransform: "none",
                          boxShadow: isSelected ? 2 : 0,
                          transition: "all 0.2s",
                          "&:hover": {
                            backgroundColor: isSelected ? "#555" : "#ccc",
                            color: isSelected ? "#fff" : "#111",
                          },
                          minWidth: 90,
                          px: 2,
                          py: 1,
                        }}
                      >
                        {`Volumen ${vol}`}
                      </Button>
                    );
                  })}
                </Box>
              </Box>
            )}

            {/* Selección de radares */}
            {Array.isArray(radars) && radars.length > 0 && (
              <Box>
                <Typography variant="subtitle1" mb={2} gutterBottom>
                  Seleccionar radares
                </Typography>
                <Box display="flex" flexWrap="wrap" gap={1}>
                  {radars.map((site) => {
                    const isSelected = selectedRadars.includes(site);
                    const atMax =
                      !isSelected && selectedRadars.length >= MAX_RADARS;
                    return (
                      <Button
                        key={site}
                        variant={isSelected ? "contained" : "outlined"}
                        disabled={atMax}
                        onClick={() => {
                          setSelectedRadars((prev) => {
                            const already = prev.includes(site);
                            if (already) return prev.filter((s) => s !== site);
                            if (prev.length >= MAX_RADARS) return prev; // ignore if at limit
                            return [...prev, site];
                          });
                        }}
                        sx={{
                          borderRadius: 999,
                          backgroundColor: isSelected ? "#888" : "#eee",
                          color: isSelected ? "#fff" : "#333",
                          fontWeight: 500,
                          textTransform: "none",
                          boxShadow: isSelected ? 2 : 0,
                          transition: "all 0.2s",
                          "&:hover": {
                            backgroundColor: isSelected ? "#555" : "#ccc",
                            color: isSelected ? "#fff" : "#111",
                          },
                          minWidth: 90,
                          px: 2,
                          py: 1,
                        }}
                      >
                        {String(site)}
                      </Button>
                    );
                  })}
                </Box>
                <Typography
                  variant="caption"
                  sx={{ opacity: 0.7, display: "block", mt: 0.5 }}
                >
                  Máximo {MAX_RADARS} radares a la vez.
                </Typography>
              </Box>
            )}
          </Box>
        </Box>

        <Divider sx={{ my: 2 }} />

        {/* Variables reales del archivo - Ocultar para COLMAX */}
        {product !== "colmax" && (
          <Box mt={2}>
            <LayerControlList items={layers} onChange={setLayers} />
          </Box>
        )}

        {isPPI && (
          <Box mt={2}>
            <Typography variant="subtitle1" gutterBottom>
              Seleccionar elevación (°)
            </Typography>
            <Box px={1}>
              <Slider
                value={elevationIdx}
                onChange={(_, v) => setElevationIdx(v)}
                step={1}
                min={0}
                max={maxIdx}
                marks={elevMarks}
                valueLabelDisplay="auto"
                valueLabelFormat={(i) => i}
              />
              <Typography variant="caption" sx={{ opacity: 0.7 }}>
                Índice de elevación seleccionado: {elevationIdx}
              </Typography>
            </Box>
          </Box>
        )}

        {isCAPPI && (
          <Box mt={2}>
            <Typography variant="subtitle1" gutterBottom>
              Seleccionar altura (m)
            </Typography>
            <Box px={1}>
              <TextField
                fullWidth
                type="number"
                variant="outlined"
                value={height}
                onChange={(e) => setHeight(Number(e.target.value))}
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end">m</InputAdornment>
                  ),
                }}
              />
            </Box>
          </Box>
        )}

        {(isPPI || isCAPPI) && <Divider sx={{ my: 2 }} />}

        {/* ---- Filtros por rango ---- */}
        <Box mt={2}>
          <Box display="flex" alignItems="center" gap={1}>
            <IconButton
              size="small"
              onClick={() => setShowFilters((v) => !v)}
              aria-label={showFilters ? "Ocultar filtros" : "Mostrar filtros"}
            >
              {showFilters ? <ExpandLessIcon /> : <ExpandMoreIcon />}
            </IconButton>
            <Typography variant="subtitle1" sx={{ userSelect: "none" }}>
              Filtros
            </Typography>
          </Box>
          <Collapse in={showFilters} timeout="auto" unmountOnExit>
            {/* RHOHV */}
            <Box mt={1} px={1}>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={!!filters.rhohv?.enabled}
                    onChange={(e) => setRhohv({ enabled: e.target.checked })}
                  />
                }
                label="RHOHV"
              />
              <Box
                display="flex"
                alignItems="center"
                gap={2}
                pl={5}
                sx={{ flexWrap: "wrap" }}
              >
                <Slider
                  value={[
                    Number(filters.rhohv?.min ?? 0),
                    Number(filters.rhohv?.max ?? 1),
                  ]}
                  onChange={(_, v) => {
                    const [min, max] = v;
                    setRhohv({ min, max });
                  }}
                  step={0.01}
                  min={0}
                  max={1}
                  marks={MARKS_01}
                  valueLabelDisplay="auto"
                  disabled={!filters.rhohv?.enabled}
                  sx={{ flex: 1, minWidth: 220 }}
                />
                <TextField
                  type="number"
                  size="small"
                  label="Min"
                  value={Number(filters.rhohv?.min ?? 0)}
                  onChange={(e) => setRhohv({ min: clamp01(e.target.value) })}
                  inputProps={{ step: 0.01, min: 0, max: 1 }}
                  disabled={!filters.rhohv?.enabled}
                />
                <TextField
                  type="number"
                  size="small"
                  label="Max"
                  value={Number(filters.rhohv?.max ?? 1)}
                  onChange={(e) => setRhohv({ max: clamp01(e.target.value) })}
                  inputProps={{ step: 0.01, min: 0, max: 1 }}
                  disabled={!filters.rhohv?.enabled}
                />
              </Box>
            </Box>

            {/* Filtros de variable seleccionada */}
            <Box mt={2} mb={2}>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={!!filters.other?.enabled}
                    onChange={(e) => setOther({ enabled: e.target.checked })}
                  />
                }
                label={`Rango de ${activeField}`}
              />
              <Box
                display="flex"
                alignItems="center"
                gap={1}
                pl={5}
              >
                <Slider
                  value={activeRange}
                  onChange={(_, v) => setActiveRange(v)}
                  step={0.1}
                  min={limits.min}
                  max={limits.max}
                  valueLabelDisplay="auto"
                  disabled={!filters.other?.enabled}
                  sx={{ flex: 1, minWidth: 180 }}
                />
                <TextField
                  size="small"
                  type="number"
                  label="Min"
                  value={activeRange[0]}
                  onChange={(e) =>
                    setActiveRange(([_, b]) => [Number(e.target.value), b])
                  }
                  disabled={!filters.other?.enabled}
                  sx={{ width: 80 }}
                />
                <TextField
                  size="small"
                  type="number"
                  label="Max"
                  value={activeRange[1]}
                  onChange={(e) =>
                    setActiveRange(([a, _]) => [a, Number(e.target.value)])
                  }
                  disabled={!filters.other?.enabled}
                  sx={{ width: 80 }}
                />
              </Box>
            </Box>
          </Collapse>
        </Box>
      </DialogContent>

      <DialogActions>
        <Button onClick={handleClose} color="secondary">
          Cancelar
        </Button>
        <Button onClick={handleAccept} variant="contained">
          Aceptar
        </Button>
      </DialogActions>
    </Dialog>
  );
}
