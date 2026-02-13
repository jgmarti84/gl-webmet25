import React from "react";
import {
  Box,
  Paper,
  RadioGroup,
  FormControlLabel,
  Radio,
  Typography,
} from "@mui/material";

// layers: array of LayerResult for current frame
// value: currently selected source_file (string)
// onChange: (source_file_string) => void
export default function ActiveLayerPicker({ layers = [], value, onChange }) {
  if (!Array.isArray(layers) || layers.length <= 1) return null;

  // Agrupar capas por archivo fuente (radar)
  const radarGroups = {};
  layers.forEach((L) => {
    const src = L?.source_file;
    if (!src) return;
    if (!radarGroups[src]) {
      radarGroups[src] = {
        value: src,
        label: buildLabel(src),
        radar: L?.radar,
      };
    }
  });

  const items = Object.values(radarGroups);

  if (items.length <= 1) return null;

  return (
    <Paper
      elevation={3}
      sx={{
        position: "fixed",
        top: 60,
        right: 12,
        zIndex: 1000,
        p: 1.5,
        maxWidth: 360,
      }}
    >
      <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
        Capa activa para herramientas
      </Typography>
      <RadioGroup
        value={value ?? items[0].value}
        onChange={(e) => onChange?.(e.target.value)}
        name="active-layer-picker"
      >
        {items.map((it) => (
          <FormControlLabel
            key={it.value}
            value={it.value}
            control={<Radio size="small" />}
            label={
              <Typography variant="body2" noWrap title={it.label}>
                {it.label}
              </Typography>
            }
          />
        ))}
      </RadioGroup>
    </Paper>
  );
}

function buildLabel(filepath) {
  // Extraer solo el nombre del archivo, sin ruta
  return basename(filepath);
}

function basename(path) {
  if (!path || typeof path !== "string") return "";
  const norm = path.replace(/\\/g, "/");
  const parts = norm.split("/");
  return parts[parts.length - 1] || path;
}
