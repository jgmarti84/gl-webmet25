import { useEffect, useMemo, useState } from "react";
import {
  Box,
  Typography,
  Slider,
  TextField,
  Checkbox,
  FormControlLabel,
  Divider,
} from "@mui/material";

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

function clamp01(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(1, n));
}

export default function RadarFilterControls({
  selectedField = "DBZH",
  onFiltersChange,
  initialFilters = {
    rhohv: { enabled: false, min: 0.92, max: 1.0 },
    other: { enabled: true, min: 0, max: 1.0 },
  },
}) {
  const activeField = String(selectedField || "DBZH").toUpperCase();
  const limits = FIELD_LIMITS[activeField] || { min: 0, max: 1 };

  const [activeRange, setActiveRange] = useState([limits.min, limits.max]);
  const [rhohv, setRhohv] = useState({
    enabled: !!initialFilters?.rhohv?.enabled,
    min: Number(initialFilters?.rhohv?.min ?? 0.92),
    max: Number(initialFilters?.rhohv?.max ?? 1.0),
  });

  // Resetear rangos cuando cambia la variable activa
  useEffect(() => {
    const l = FIELD_LIMITS[activeField] || { min: 0, max: 1 };
    setActiveRange([l.min, l.max]);
  }, [activeField]);

  // Emitir filtros hacia arriba cada vez que cambie algo
  useEffect(() => {
    const [amin, amax] = activeRange;

    const out = [
      {
        field: activeField,
        type: "range",
        min: Number(amin),
        max: Number(amax),
        enabled: true,
      },
    ];

    // RHOHV: disponible siempre. Si el activo NO es RHOHV, suele ser tu QC obligado;
    // si ES RHOHV, solo se aplica si lo activás explícitamente.
    if (rhohv.enabled) {
      let rmin = clamp01(rhohv.min);
      let rmax = clamp01(rhohv.max);
      if (rmin > rmax) [rmin, rmax] = [rmax, rmin];
      out.push({
        field: "RHOHV",
        type: "range",
        min: rmin,
        max: rmax,
        enabled: true,
      });
    }

    onFiltersChange?.(out);
  }, [
    activeField,
    activeRange,
    rhohv.enabled,
    rhohv.min,
    rhohv.max,
    onFiltersChange,
  ]);

  return (
    <Box
      mt={2}
      sx={{
        "& .MuiFormControlLabel-root": { m: 0.2 },
        "& .MuiSlider-root": { height: 4 }, // slider más fino
        "& .MuiTextField-root": { width: 80, m: 0.2 },
        "& .MuiTypography-subtitle1": { fontSize: "0.9rem" },
      }}
    >
      <Divider sx={{ my: 2 }} />

      <Typography variant="subtitle1" gutterBottom>
        Filtros
      </Typography>

      {/* ---- RHOHV ---- */}
      {selectedField !== "RHOHV" && (
        <Box mt={1} px={1}>
          <Box
            display="flex"
            alignItems="center"
            gap={2}
            sx={{ flexWrap: "wrap" }}
          >
            <FormControlLabel
              control={
                <Checkbox
                  checked={!!rhohv.enabled}
                  onChange={(e) =>
                    setRhohv((prev) => ({ ...prev, enabled: e.target.checked }))
                  }
                />
              }
              label="RHOHV"
            />
            <Slider
              value={[Number(rhohv.min ?? 0.92), Number(rhohv.max ?? 1.0)]}
              onChange={(_, v) => {
                const [min, max] = v;
                setRhohv((prev) => ({ ...prev, min, max }));
              }}
              step={0.01}
              min={0}
              max={1}
              marks={MARKS_01}
              valueLabelDisplay="auto"
              disabled={!rhohv.enabled}
              sx={{ width: 353, mr: 6, ml: 6 }}
            />
            <TextField
              type="number"
              size="small"
              label="Min"
              value={Number(rhohv.min ?? 0.92)}
              onChange={(e) =>
                setRhohv((prev) => ({ ...prev, min: clamp01(e.target.value) }))
              }
              inputProps={{ step: 0.01, min: 0, max: 1 }}
              disabled={!rhohv.enabled}
            />
            <TextField
              type="number"
              size="small"
              label="Max"
              value={Number(rhohv.max ?? 1)}
              onChange={(e) =>
                setRhohv((prev) => ({ ...prev, max: clamp01(e.target.value) }))
              }
              inputProps={{ step: 0.01, min: 0, max: 1 }}
              disabled={!rhohv.enabled}
            />
          </Box>
        </Box>
      )}

      {/* ---- Rango de variable activa ---- */}
      <Box
        mt={3}
        mb={2}
        display="flex"
        alignItems="center"
        gap={3}
        pl={4}
        sx={{ flexWrap: "wrap" }}
      >
        <Typography variant="subtitle1">Rango de {activeField}</Typography>
        <Box px={1} display="flex" alignItems="center" gap={2}>
          <Slider
            value={activeRange}
            onChange={(_, v) => setActiveRange(v)}
            step={0.1}
            min={limits.min}
            max={limits.max}
            valueLabelDisplay="auto"
            sx={{ flex: 1, minWidth: 220, mr: 6, ml: 1 }}
          />
          <TextField
            size="small"
            type="number"
            label="Min"
            value={activeRange[0]}
            onChange={(e) =>
              setActiveRange(([_, b]) => [Number(e.target.value), b])
            }
          />
          <TextField
            size="small"
            type="number"
            label="Max"
            value={activeRange[1]}
            onChange={(e) =>
              setActiveRange(([a, _]) => [a, Number(e.target.value)])
            }
          />
        </Box>
      </Box>
    </Box>
  );
}
