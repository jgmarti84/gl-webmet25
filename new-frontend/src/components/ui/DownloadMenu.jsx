import { useState } from "react";
import {
  Menu,
  MenuItem,
  ListItemIcon,
  ListItemText,
  Divider,
  Typography,
  Box,
} from "@mui/material";
import DownloadIcon from "@mui/icons-material/Download";
import ImageIcon from "@mui/icons-material/Image";
import MapIcon from "@mui/icons-material/Map";
import ShowChartIcon from "@mui/icons-material/ShowChart";

/**
 * DownloadMenu - Menú desplegable de opciones de descarga
 *
 * Props:
 * - anchorEl: Elemento ancla del menú
 * - open: Booleano que indica si está abierto
 * - onClose: Función para cerrar el menú
 * - availableDownloads: Objeto con funciones de descarga disponibles
 *   {
 *     mapScreenshot: { handler: fn, label: string, disabled: bool },
 *     cogLayers: { handler: fn, label: string, disabled: bool },
 *     rhiImage: { handler: fn, label: string, disabled: bool },
 *     statsData: { handler: fn, label: string, disabled: bool },
 *   }
 */
export default function DownloadMenu({
  anchorEl,
  open,
  onClose,
  availableDownloads = {},
}) {
  const { mapScreenshot, cogLayers, rhiImage, statsData } = availableDownloads;

  const hasAnyDownload = Object.values(availableDownloads).some(
    (item) => item && !item.disabled
  );

  return (
    <Menu
      anchorEl={anchorEl}
      open={open}
      onClose={onClose}
      anchorOrigin={{
        vertical: "bottom",
        horizontal: "right",
      }}
      transformOrigin={{
        vertical: "top",
        horizontal: "right",
      }}
      PaperProps={{
        elevation: 3,
        sx: {
          minWidth: 240,
          mt: 1,
        },
      }}
    >
      <Box sx={{ px: 2, py: 1 }}>
        <Typography variant="subtitle2" color="text.secondary">
          Descargas disponibles
        </Typography>
      </Box>
      <Divider />

      {!hasAnyDownload && (
        <MenuItem disabled>
          <ListItemText
            primary="No hay descargas disponibles"
            primaryTypographyProps={{
              variant: "body2",
              color: "text.secondary",
            }}
          />
        </MenuItem>
      )}

      {mapScreenshot && (
        <MenuItem
          onClick={() => {
            mapScreenshot.handler?.();
            onClose();
          }}
          disabled={mapScreenshot.disabled}
        >
          <ListItemIcon>
            <MapIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText
            primary={mapScreenshot.label || "Captura del mapa"}
            secondary="PNG de alta calidad"
            secondaryTypographyProps={{ variant: "caption" }}
          />
        </MenuItem>
      )}

      {cogLayers && (
        <MenuItem
          onClick={() => {
            cogLayers.handler?.();
            onClose();
          }}
          disabled={cogLayers.disabled}
        >
          <ListItemIcon>
            <ImageIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText
            primary={cogLayers.label || "Capas COG/GeoTIFF"}
            secondary="Archivos georeferenciados"
            secondaryTypographyProps={{ variant: "caption" }}
          />
        </MenuItem>
      )}

      {rhiImage && (
        <>
          <Divider sx={{ my: 0.5 }} />
          <MenuItem
            onClick={() => {
              rhiImage.handler?.();
              onClose();
            }}
            disabled={rhiImage.disabled}
          >
            <ListItemIcon>
              <ShowChartIcon fontSize="small" />
            </ListItemIcon>
            <ListItemText
              primary={rhiImage.label || "Corte vertical (RHI)"}
              secondary="Imagen PNG del perfil"
              secondaryTypographyProps={{ variant: "caption" }}
            />
          </MenuItem>
        </>
      )}

      {statsData && (
        <MenuItem
          onClick={() => {
            statsData.handler?.();
            onClose();
          }}
          disabled={statsData.disabled}
        >
          <ListItemIcon>
            <DownloadIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText
            primary={statsData.label || "Datos de estadísticas"}
            secondary="JSON con resultados"
            secondaryTypographyProps={{ variant: "caption" }}
          />
        </MenuItem>
      )}
    </Menu>
  );
}
