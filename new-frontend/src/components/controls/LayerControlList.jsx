import React, { useCallback, useState } from "react";
import PropTypes from "prop-types";
import {
  Box,
  Checkbox,
  IconButton,
  List,
  ListItem,
  ListItemText,
  Slider,
  Typography,
  Divider,
  Tooltip,
  Button,
} from "@mui/material";
import DragIndicatorIcon from "@mui/icons-material/DragIndicator";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";

/**
 * items: [
 *   { id: 'colmax', label: 'COLMAX(Z)', enabled: true, opacity: 1 },
 *   { id: 'kdp0.5', label: 'KDP@0.5', enabled: false, opacity: 0.8 },
 *   ...
 * ]
 *
 * onChange(nextItems) -> devuelve lista actualizada (orden/estado/opacity)
 */
function LayerControlList({ title = "Variables de Radar", items, onChange, initialVisible = 4 }) {
  const [isExpanded, setIsExpanded] = useState(false);

  // Reordenar items para priorizar DBZH, ZDR, RHOHV, KDP
  const priorityFields = ['DBZH', 'ZDR', 'RHOHV', 'KDP'];
  const sortedItems = React.useMemo(() => {
    const priority = [];
    const rest = [];

    items.forEach(item => {
      const fieldName = item.field || item.label.toUpperCase();
      if (priorityFields.includes(fieldName)) {
        priority.push(item);
      } else {
        rest.push(item);
      }
    });

    // Ordenar priority según el orden en priorityFields
    priority.sort((a, b) => {
      const aField = a.field || a.label.toUpperCase();
      const bField = b.field || b.label.toUpperCase();
      return priorityFields.indexOf(aField) - priorityFields.indexOf(bField);
    });

    return [...priority, ...rest];
  }, [items]);

  // Determinar qué elementos mostrar
  const visibleItems = isExpanded ? sortedItems : sortedItems.slice(0, initialVisible);
  const hasMoreItems = sortedItems.length > initialVisible;

  // --- Drag & Drop (HTML5 nativo) ---
  const onDragStart = useCallback((e, fromIdx) => {
    e.dataTransfer.setData("text/plain", String(fromIdx));
    e.dataTransfer.effectAllowed = "move";
  }, []);

  const onDragOver = useCallback((e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }, []);

  const onDrop = useCallback(
    (e, toIdx) => {
      e.preventDefault();
      const fromIdx = Number(e.dataTransfer.getData("text/plain"));
      if (Number.isNaN(fromIdx) || fromIdx === toIdx) return;

      // Si la lista está colapsada, solo permitir reordenar dentro de los elementos visibles
      if (!isExpanded && (fromIdx >= initialVisible || toIdx >= initialVisible)) {
        return;
      }

      const next = sortedItems.slice();
      const [moved] = next.splice(fromIdx, 1);
      next.splice(toIdx, 0, moved);
      onChange(next);
    },
    [sortedItems, onChange, isExpanded, initialVisible]
  );

  const toggleEnabled = (idx) => {
    const next = sortedItems.slice();
    const currentEnabledCount = next.filter((l) => l.enabled).length;

    // Si intenta habilitar y ya hay 3 habilitadas no permitir
    if (!next[idx].enabled && currentEnabledCount >= 3) {
      alert("Solo se pueden habilitar hasta 3 capas al mismo tiempo.");
      return;
    }

    next[idx] = { ...next[idx], enabled: !next[idx].enabled };
    onChange(next);
  };

  const changeOpacity = (idx, value) => {
    const next = sortedItems.slice();
    next[idx] = { ...next[idx], opacity: value };
    onChange(next);
  };

  return (
    <Box>
      <Typography
        variant="subtitle1"
        sx={{
          mb: 1,
          p: 1,
        }}
      >
        {title}
      </Typography>

      {items.length === 0 && (
        <Typography variant="body2" sx={{ p: 1 }}>
          No hay productos disponibles
        </Typography>
      )}

      <List disablePadding>
        {sortedItems.length > 0 &&
          visibleItems.map((it, displayIdx) => {
            // El índice real en el array completo
            const actualIdx = sortedItems.findIndex(item => item.id === it.id);

            return (
              <Box
                key={it.id}
                draggable
                onDragStart={(e) => onDragStart(e, actualIdx)}
                onDragOver={onDragOver}
                onDrop={(e) => onDrop(e, actualIdx)}
                sx={{
                  px: 1,
                  py: 0.5,
                  width: "90%",
                  bgcolor: "background.paper",
                }}
              >
                {/* Checkbox + Nombre + Slider + Manija en una sola línea */}
                <Box display="flex" alignItems="center" gap={1}>
                  <Checkbox
                    checked={!!it.enabled}
                    onChange={() => toggleEnabled(actualIdx)}
                    disabled={
                      !it.enabled && sortedItems.filter((l) => l.enabled).length >= 3
                    }
                    inputProps={{ "aria-label": `activar ${it.label}` }}
                  />

                  <Typography variant="body2" sx={{ minWidth: 80 }}>
                    {it.label}
                  </Typography>

                  <Slider
                    value={Number(it.opacity ?? 1)}
                    onChange={(_, v) => changeOpacity(actualIdx, v)}
                    min={0}
                    max={1}
                    step={0.01}
                    valueLabelDisplay="auto"
                    sx={{ flex: 1 }}
                  />

                  <Tooltip title="Arrastrar para cambiar el orden">
                    <IconButton size="small" sx={{ cursor: "grab", px: 1 }}>
                      <DragIndicatorIcon />
                    </IconButton>
                  </Tooltip>
                </Box>
              </Box>
            );
          })}
      </List>

      {/* Botón para expandir/colapsar */}
      {hasMoreItems && (
        <Box display="flex" justifyContent="center" mt={1}>
          <Button
            size="small"
            onClick={() => setIsExpanded(!isExpanded)}
            startIcon={isExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
            sx={{ textTransform: "none" }}
          >
            {isExpanded
              ? "Mostrar menos"
              : `Mostrar ${sortedItems.length - initialVisible} más`}
          </Button>
        </Box>
      )}

      <Divider sx={{ mt: 1 }} />
    </Box>
  );
}

LayerControlList.propTypes = {
  title: PropTypes.string,
  items: PropTypes.arrayOf(
    PropTypes.shape({
      id: PropTypes.string.isRequired,
      label: PropTypes.string.isRequired,
      enabled: PropTypes.bool.isRequired,
      opacity: PropTypes.number.isRequired, // 0..1
    })
  ).isRequired,
  onChange: PropTypes.func.isRequired,
  initialVisible: PropTypes.number, // Número de elementos visibles inicialmente
};

export default LayerControlList;
