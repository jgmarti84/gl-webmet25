import { useState } from "react";
import { Box, IconButton, Paper, Tooltip, Zoom } from "@mui/material";
import { useSnackbar } from "notistack";
import ScreenshotMonitorIcon from "@mui/icons-material/ScreenshotMonitor";
import PrintIcon from "@mui/icons-material/Print";
import FullscreenIcon from "@mui/icons-material/Fullscreen";
import FullscreenExitIcon from "@mui/icons-material/FullscreenExit";
import BuildIcon from "@mui/icons-material/Build";
import DownloadIcon from "@mui/icons-material/Download";
import VerticalSplitIcon from "@mui/icons-material/VerticalSplit";
import LockIcon from "@mui/icons-material/Lock";
import LockOpenIcon from "@mui/icons-material/LockOpen";
import DownloadMenu from "../ui/DownloadMenu";

/**
 * MapToolbar - Barra de herramientas horizontal superior derecha
 *
 * Props:
 * - onScreenshot: función para capturar pantalla
 * - onPrint: función para imprimir
 * - onFullscreen: función para alternar pantalla completa
 * - isFullscreen: booleano que indica si está en pantalla completa
 * - availableDownloads: objeto con opciones de descarga disponibles
 * - isSplitScreen: booleano que indica si está en modo split screen
 * - showSplitButton: booleano para mostrar botón de split
 * - showLockButton: booleano para mostrar botón de lock
 * - locked: booleano que indica si los mapas están sincronizados
 * - onToggleSplit: función para alternar split screen
 * - onToggleLock: función para alternar lock de sincronización
 */
export default function MapToolbar({
  onScreenshot,
  onPrint,
  onFullscreen,
  isFullscreen = false,
  availableDownloads = {},
  isSplitScreen = false,
  showSplitButton = true,
  showLockButton = false,
  locked = false,
  onToggleSplit,
  onToggleLock,
}) {
  const [expanded, setExpanded] = useState(false);
  const [downloadMenuAnchor, setDownloadMenuAnchor] = useState(null);
  const { enqueueSnackbar } = useSnackbar();

  const handleScreenshotClick = async () => {
    try {
      await onScreenshot?.();
      enqueueSnackbar("Captura de pantalla guardada", { variant: "success" });
    } catch {
      enqueueSnackbar("Error al capturar pantalla", { variant: "error" });
    }
  };

  const handlePrintClick = () => {
    try {
      onPrint?.();
    } catch {
      enqueueSnackbar("Error al imprimir", { variant: "error" });
    }
  };

  const handleFullscreenClick = async () => {
    try {
      await onFullscreen?.();
    } catch {
      enqueueSnackbar("Error al cambiar pantalla completa", {
        variant: "error",
      });
    }
  };

  const handleDownloadClick = (event) => {
    setDownloadMenuAnchor(event.currentTarget);
  };

  const handleCloseDownloadMenu = () => {
    setDownloadMenuAnchor(null);
  };

  const hasDownloads = Object.keys(availableDownloads).length > 0;

  const handleSplitClick = () => {
    try {
      onToggleSplit?.();
      enqueueSnackbar(
        isSplitScreen
          ? "Pantalla simple activada"
          : "Pantalla dividida activada",
        { variant: "info" }
      );
    } catch {
      enqueueSnackbar("Error al cambiar modo de pantalla", {
        variant: "error",
      });
    }
  };

  const handleLockClick = () => {
    try {
      onToggleLock?.();
      enqueueSnackbar(
        locked ? "Sincronización desactivada" : "Sincronización activada",
        { variant: "info" }
      );
    } catch {
      enqueueSnackbar("Error al cambiar sincronización", { variant: "error" });
    }
  };

  const tools = [
    ...(showSplitButton
      ? [
          {
            icon: <VerticalSplitIcon />,
            tooltip: isSplitScreen ? "Pantalla simple" : "Dividir pantalla",
            action: handleSplitClick,
            active: isSplitScreen,
          },
        ]
      : []),
    ...(showLockButton
      ? [
          {
            icon: locked ? <LockIcon /> : <LockOpenIcon />,
            tooltip: locked ? "Desbloquear mapas" : "Bloquear mapas",
            action: handleLockClick,
            active: locked,
          },
        ]
      : []),
    {
      icon: <ScreenshotMonitorIcon />,
      tooltip: "Capturar pantalla",
      action: handleScreenshotClick,
    },
    ...(hasDownloads
      ? [
          {
            icon: <DownloadIcon />,
            tooltip: "Descargas",
            action: handleDownloadClick,
          },
        ]
      : []),
    {
      icon: <PrintIcon />,
      tooltip: "Imprimir",
      action: handlePrintClick,
    },
    {
      icon: isFullscreen ? <FullscreenExitIcon /> : <FullscreenIcon />,
      tooltip: isFullscreen ? "Salir pantalla completa" : "Pantalla completa",
      action: handleFullscreenClick,
    },
  ];

  const toggleExpanded = () => {
    setExpanded(!expanded);
  };

  return (
    <Paper
      elevation={0}
      className="no-print"
      sx={{
        position: "absolute",
        top: 12,
        right: 12,
        zIndex: 1000,
        display: "flex",
        flexDirection: "row",
        alignItems: "center",
        backgroundColor: "#fff",
        borderRadius: "8px",
        padding: "4px",
        gap: "4px",
      }}
    >
      {/* Botón de herramienta (toggle) */}
      <Tooltip
        title={expanded ? "Ocultar herramientas" : "Mostrar herramientas"}
        placement="left"
      >
        <IconButton
          onClick={toggleExpanded}
          sx={{
            width: 30,
            height: 30,
            borderRadius: "6px",
            color: "#000",
            backgroundColor: expanded ? "rgba(0, 0, 0, 0.08)" : "transparent",
            transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
            transform: expanded ? "rotate(90deg)" : "rotate(0deg)",
            "& .MuiSvgIcon-root": {
              fontSize: "1.25rem",
            },
            "&:hover": {
              backgroundColor: "rgba(0, 0, 0, 0.08)",
            },
          }}
        >
          <BuildIcon />
        </IconButton>
      </Tooltip>

      {/* Herramientas expandibles */}
      <Box
        sx={{
          display: "flex",
          flexDirection: "row",
          gap: "4px",
          overflow: "hidden",
          maxWidth: expanded ? "250px" : "0px",
          transition: "max-width 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
        }}
      >
        {tools.map((tool, index) => (
          <Zoom
            key={index}
            in={expanded}
            style={{
              transitionDelay: expanded ? `${index * 50}ms` : "0ms",
            }}
          >
            <Tooltip title={tool.tooltip} placement="bottom">
              <IconButton
                onClick={tool.action}
                sx={{
                  width: 30,
                  height: 30,
                  borderRadius: "6px",
                  color: "#000",
                  backgroundColor: tool.active
                    ? "rgba(74, 144, 226, 0.2)"
                    : "transparent",
                  transition: "all 0.2s ease",
                  "& .MuiSvgIcon-root": {
                    fontSize: "1.25rem",
                  },
                  "&:hover": {
                    backgroundColor: tool.active
                      ? "rgba(74, 144, 226, 0.3)"
                      : "rgba(0, 0, 0, 0.08)",
                    transform: "scale(1.05)",
                  },
                }}
              >
                {tool.icon}
              </IconButton>
            </Tooltip>
          </Zoom>
        ))}
      </Box>

      {/* Menú de descargas */}
      <DownloadMenu
        anchorEl={downloadMenuAnchor}
        open={Boolean(downloadMenuAnchor)}
        onClose={handleCloseDownloadMenu}
        availableDownloads={availableDownloads}
      />
    </Paper>
  );
}
