import { useEffect, useState, useRef } from "react";
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Box,
  Typography,
  Paper,
  CircularProgress,
  IconButton,
} from "@mui/material";
import { Close as CloseIcon, Add as AddIcon } from "@mui/icons-material";
import Draggable from "react-draggable";
import ElevationChart from "../ui/ElevationChart";

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

/**
 * Props:
 * - open: boolean
 * - onClose: () => void
 * - onRequestDraw: () => void - solicitar que el usuario dibuje una línea
 * - drawnCoordinates: {lat, lon}[] - coordenadas dibujadas por el usuario
 * - onGenerate: (coordinates) => Promise<response>
 * - onClearDrawing: () => void - limpiar el dibujo del mapa
 * - onHighlightPoint: (lat, lon) => void - resaltar un punto en el mapa
 */
export default function ElevationProfileDialog({
  open,
  onClose,
  onRequestDraw,
  drawnCoordinates = [],
  drawingFinished = false,
  onGenerate,
  onClearDrawing,
  onHighlightPoint,
  onProfileGenerated,
}) {
  const [loading, setLoading] = useState(false);
  const [profileData, setProfileData] = useState(null);
  const [error, setError] = useState("");
  const [isDrawing, setIsDrawing] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [expandedChart, setExpandedChart] = useState(false);

  // Limpiar al cerrar
  const handleClose = () => {
    setProfileData(null);
    setError("");
    setIsDrawing(false);
    setIsMinimized(false);
    onClearDrawing?.();
    onClose();
  };

  // Iniciar modo dibujo
  const handleStartDrawing = () => {
    setProfileData(null);
    setError("");
    setIsDrawing(true);
    setIsMinimized(true); // Minimizar el diálogo
    onRequestDraw?.();
  };

  // Generar perfil cuando el usuario completa el dibujo
  useEffect(() => {
    if (!drawingFinished || !drawnCoordinates || drawnCoordinates.length < 2) {
      return;
    }

    const generateProfile = async () => {
      setIsDrawing(false);
      setIsMinimized(false); // Restaurar el diálogo
      setLoading(true);
      setError("");

      try {
        const response = await onGenerate(drawnCoordinates);
        setProfileData(response.data);
        onProfileGenerated?.(); // Notificar que se generó el perfil
      } catch (err) {
        setError(err?.response?.data?.detail || String(err));
        onProfileGenerated?.(); // Notificar incluso si hay error
      } finally {
        setLoading(false);
      }
    };

    generateProfile();
  }, [drawingFinished, drawnCoordinates, onGenerate, onProfileGenerated]);

  // Manejar hover en el gráfico
  const handleHover = (point) => {
    onHighlightPoint?.(point?.lat || null, point?.lon || null);
  };

  // Calcular ancho dinámico basado en la distancia total
  const calculateDialogWidth = () => {
    if (!profileData?.profile || profileData.profile.length === 0) {
      return "sm";
    }
    const lastPoint = profileData.profile[profileData.profile.length - 1];
    const totalDistance = lastPoint?.distance || 0;

    // Escalar el ancho según la distancia
    if (totalDistance < 80) return "sm"; // ~600px
    if (totalDistance < 600) return "md"; // ~900px
    if (totalDistance < 900) return "lg"; // ~1200px
    return "xl"; // ~1536px
  };

  return (
    <>
      <Dialog
        open={open && !isMinimized}
        onClose={handleClose}
        fullWidth
        maxWidth={calculateDialogWidth()}
        hideBackdrop
        disableEnforceFocus
        disableAutoFocus
        disableRestoreFocus
        disableScrollLock
        slotProps={{
          root: { sx: { pointerEvents: "none" } },
        }}
        PaperProps={{
          sx: { pointerEvents: "auto", minHeight: "320px" },
        }}
        PaperComponent={PaperComponent}
        aria-labelledby="draggable-dialog-title"
      >
        <DialogTitle
          id="draggable-dialog-title"
          sx={{
            cursor: "move",
            backgroundColor: "#f5f5f5",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            paddingRight: 0.5,
            paddingTop: 0.5,
            paddingBottom: 0.5,
          }}
        >
          <Typography
            variant="subtitle2"
            component="span"
            sx={{ fontWeight: 600 }}
          >
            Perfil de Elevación
          </Typography>
          <Box sx={{ display: "flex", gap: 0.5 }}>
            {profileData && (
              <IconButton
                onClick={handleStartDrawing}
                color="primary"
                size="small"
                title="Dibujar nueva línea"
                sx={{
                  "& .MuiSvgIcon-root": {
                    fontSize: "1.25rem",
                  },
                }}
              >
                <AddIcon />
              </IconButton>
            )}
            <IconButton
              onClick={handleClose}
              color="secondary"
              size="small"
              title="Cerrar"
              sx={{
                "& .MuiSvgIcon-root": {
                  fontSize: "1.25rem",
                },
              }}
            >
              <CloseIcon />
            </IconButton>
          </Box>
        </DialogTitle>

        <DialogContent dividers sx={{ minHeight: "250px" }}>
          {!profileData && !loading && !error && (
            <Box
              sx={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                height: "100%",
                minHeight: "220px",
              }}
            >
              <Typography variant="body1" sx={{ mb: 2 }}>
                {isDrawing
                  ? "Haz click en el mapa para agregar puntos. Click en el cuadrado blanco para terminar."
                  : "Dibuja una línea en el mapa para generar el perfil de elevación."}
              </Typography>
              {!isDrawing && (
                <Button variant="contained" onClick={handleStartDrawing}>
                  Comenzar a dibujar
                </Button>
              )}
              <Typography
                variant="caption"
                sx={{ mt: 2, color: "text.secondary" }}
              >
                Atajos: ESC para cancelar, Enter para terminar, Delete para borrar
                último punto
              </Typography>
            </Box>
          )}

          {loading && (
            <Box
              sx={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                height: "100%",
                minHeight: "220px",
              }}
            >
              <CircularProgress />
              <Typography sx={{ mt: 2 }}>
                Generando perfil de elevación...
              </Typography>
            </Box>
          )}

          {error && (
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                height: "100%",
              }}
            >
              <Typography color="error">{error}</Typography>
            </Box>
          )}

          {profileData &&
            profileData.profile &&
            profileData.profile.length > 0 && (
              <Box>
                <ElevationChart
                  profileData={profileData.profile}
                  height={250}
                  onHover={handleHover}
                  clickable={true}
                  onClick={() => setExpandedChart(true)}
                />
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ mt: 1, display: "block", textAlign: "center" }}
                >
                  Haz clic en el gráfico para verlo más grande
                </Typography>
              </Box>
            )}

          {profileData &&
            profileData.profile &&
            profileData.profile.length === 0 && (
              <Box
                sx={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  height: "100%",
                }}
              >
                <Typography>
                  No se pudo obtener datos de elevación para la línea dibujada.
                </Typography>
              </Box>
            )}
        </DialogContent>
      </Dialog>

      {/* Modal para ver gráfico expandido */}
      <Dialog
        open={expandedChart}
        onClose={() => setExpandedChart(false)}
        maxWidth="xl"
        fullWidth
      >
        <DialogTitle>Perfil de elevación del terreno (expandido)</DialogTitle>
        <DialogContent>
          <Box sx={{ minHeight: "58vh", py: 2 }}>
            {profileData?.profile && (
              <ElevationChart
                profileData={profileData.profile}
                height={500}
                onHover={handleHover}
                clickable={false}
              />
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setExpandedChart(false)} variant="contained">
            Cerrar
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
