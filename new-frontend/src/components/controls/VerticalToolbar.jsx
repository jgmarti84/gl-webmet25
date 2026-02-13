import { Box, IconButton, Paper, Tooltip } from "@mui/material";
import VisibilityIcon from "@mui/icons-material/Visibility";
import ContentCutIcon from "@mui/icons-material/ContentCut";
import PercentIcon from "@mui/icons-material/Percent";
import ImageSearchIcon from "@mui/icons-material/ImageSearch";
import LayersIcon from "@mui/icons-material/Layers";
import TimelineIcon from "@mui/icons-material/Timeline";
import MapIcon from "@mui/icons-material/Map";
import PaletteIcon from "@mui/icons-material/Palette";

export default function VerticalToolbar({
  onChangeProductClick,
  onPseudoRhiClick,
  onAreaStatsClick,
  onPixelStatToggle,
  onMapSelectorToggle,
  onPaletteSelectorToggle,
  onElevationProfileClick,
  onLayerManagerToggle,
  pixelStatActive = false,
  mapSelectorActive = false,
  paletteSelectorActive = false,
  layerManagerActive = false,
}) {
  const tools = [
    {
      icon: <VisibilityIcon />,
      tooltip: "Opciones de visualización",
      action: onChangeProductClick,
      active: false,
    },
    {
      icon: <LayersIcon />,
      tooltip: "Capas",
      action: onLayerManagerToggle,
      active: layerManagerActive,
    },
    {
      icon: <MapIcon />,
      tooltip: "Mapas base",
      action: onMapSelectorToggle,
      active: mapSelectorActive,
    },
    {
      icon: <PaletteIcon />,
      tooltip: "Paletas de colores",
      action: onPaletteSelectorToggle,
      active: paletteSelectorActive,
    },
    {
      icon: <ContentCutIcon />,
      tooltip: "Generar Pseudo-RHI",
      action: onPseudoRhiClick,
      active: false,
    },
    {
      icon: <PercentIcon />,
      tooltip: "Estadísticas de área",
      action: onAreaStatsClick,
      active: false,
    },
    {
      icon: <ImageSearchIcon />,
      tooltip: "Ver valor pixel",
      action: onPixelStatToggle,
      active: pixelStatActive,
    },
    {
      icon: <TimelineIcon />,
      tooltip: "Perfil de elevación",
      action: onElevationProfileClick,
      active: false,
    },
  ];

  return (
    <Paper
      elevation={0}
      sx={{
        position: "absolute",
        top: 70, // Debajo del HeaderCard
        left: 12,
        zIndex: 1000,
        display: "flex",
        flexDirection: "column",
        backgroundColor: "transparent",
        backdropFilter: "none",
        borderRadius: "8px",
        boxShadow: "none",
        padding: "8px 0",
      }}
    >
      {tools.map((tool, index) => (
        <Box key={index}>
          <Tooltip title={tool.tooltip} placement="right">
            <IconButton
              onClick={tool.action}
              sx={{
                width: 30,
                height: 30,
                borderRadius: "8px",
                margin: "2px 7px",
                color: "#fff",
                backgroundColor: tool.active
                  ? "rgba(74, 144, 226, 1)"
                  : "rgba(74, 144, 226, 0.85)",
                boxShadow: "0 2px 6px rgba(0,0,0,0.2)",
                transition: "all 0.2s ease",
                "& .MuiSvgIcon-root": {
                  fontSize: "1.25rem", // Mantiene el tamaño del icono
                },
                "&:hover": {
                  backgroundColor: "rgba(74, 144, 226, 1)",
                  boxShadow: "0 3px 8px rgba(0,0,0,0.3)",
                  transform: "scale(1.02)",
                },
              }}
            >
              {tool.icon}
            </IconButton>
          </Tooltip>
          {/* Divider opcional después del 4to elemento (después de paletas) */}
          {index === 3 && (
            <Box
              sx={{
                height: "1px",
                backgroundColor: "rgba(255, 255, 255, 0.2)",
                margin: "4px 12px",
              }}
            />
          )}
        </Box>
      ))}
    </Paper>
  );
}
