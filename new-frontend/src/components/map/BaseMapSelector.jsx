import {
  Box,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Paper,
  Typography,
  IconButton,
  Collapse,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import CheckIcon from "@mui/icons-material/Check";

// Import images
import argenmapImg from "../../assets/argenmap.webp";
import argenmapGrisImg from "../../assets/argenmap-gris.webp";
import argenmapOscuroImg from "../../assets/argenmap-oscuro.webp";
import argenmapTopoImg from "../../assets/argenmap-topo.webp";
import esriImg from "../../assets/esri.webp";
import esritImg from "../../assets/esrit.webp";
import bingImg from "../../assets/bing.webp";

const baseMaps = [
  {
    id: "osm",
    name: "Mapa Base",
    url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    image: argenmapImg,
  },
  {
    id: "argenmap",
    name: "Argenmap",
    url: "https://wms.ign.gob.ar/geoserver/gwc/service/tms/1.0.0/capabaseargenmap@EPSG%3A3857@png/{z}/{x}/{-y}.png",
    attribution:
      '<a href="https://www.ign.gob.ar/AreaServicios/Argenmap/IntroduccionV2" target="_blank">Instituto Geográfico Nacional</a> + <a href="https://www.osm.org/copyright" target="_blank">OpenStreetMap</a>',
    image: argenmapImg,
  },
  {
    id: "argenmap-gris",
    name: "Argenmap gris",
    url: "https://wms.ign.gob.ar/geoserver/gwc/service/tms/1.0.0/mapabase_gris@EPSG%3A3857@png/{z}/{x}/{-y}.png",
    attribution:
      "<a href='https://www.ign.gob.ar/AreaServicios/Argenmap/IntroduccionV2' target='_blank'>Instituto Geográfico Nacional</a> + <a href='https://www.osm.org/copyright' target='_blank'>OpenStreetMap</a>",
    image: argenmapGrisImg,
  },
  {
    id: "argenmap-oscuro",
    name: "Argenmap oscuro",
    url: "https://wms.ign.gob.ar/geoserver/gwc/service/tms/1.0.0/argenmap_oscuro@EPSG%3A3857@png/{z}/{x}/{-y}.png", // Cambiar por URL real
    attribution:
      "<a href='https://www.ign.gob.ar/AreaServicios/Argenmap/IntroduccionV2' target='_blank'>Instituto Geográfico Nacional</a> + <a href='https://www.osm.org/copyright' target='_blank'>OpenStreetMap</a>",
    image: argenmapOscuroImg,
  },
  {
    id: "topografico",
    name: "Argenmap topográfico",
    url: "https://wms.ign.gob.ar/geoserver/gwc/service/tms/1.0.0/mapabase_topo@EPSG%3A3857@png/{z}/{x}/{-y}.png",
    attribution:
      "<a href='https://www.ign.gob.ar/AreaServicios/Argenmap/IntroduccionV2' target='_blank'>Instituto Geográfico Nacional</a> + <a href='https://www.osm.org/copyright' target='_blank'>OpenStreetMap</a>",
    image: argenmapTopoImg,
  },
  {
    id: "satellite",
    name: "Imágenes satelitales Esri",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "Esri",
    image: esriImg,
  },
  {
    id: "topo-esri",
    name: "Mapa topográfico Esri",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Physical_Map/MapServer/tile/{z}/{y}/{x}",
    attribution: "Esri",
    image: esritImg,
  },
  {
    id: "ocean",
    name: "Mapa Esri Fondo Oceánico",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}",
    attribution: "Esri",
    image: esritImg,
  },
];

export default function BaseMapSelector({
  open,
  onClose,
  selectedMap,
  onSelectMap,
}) {
  const handleSelect = (map) => {
    onSelectMap(map);
  };

  return (
    <Collapse
      in={open}
      orientation="horizontal"
      timeout={200}
      easing={{
        enter: "cubic-bezier(0.4, 0, 0.2, 1)",
        exit: "cubic-bezier(0.4, 0, 0.6, 1)",
      }}
    >
      <Paper
        elevation={3}
        sx={{
          position: "absolute",
          top: 70,
          left: 68, // A la derecha del VerticalToolbar
          zIndex: 999,
          width: 280,
          maxHeight: "calc(100vh - 100px)",
          overflowY: "auto",
          backgroundColor: "rgba(255, 255, 255, 0.98)",
          backdropFilter: "blur(8px)",
          borderRadius: "8px",
          boxShadow: "0 4px 12px rgba(0,0,0,0.2)",
          transition: "opacity 0.4s cubic-bezier(0.4, 0, 0.2, 1)",
        }}
      >
        {/* Header */}
        <Box
          sx={{
            padding: "12px 16px",
            borderBottom: "1px solid rgba(0, 0, 0, 0.08)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <Typography
            variant="subtitle1"
            sx={{
              fontWeight: 600,
              fontSize: "14px",
              color: "#212121",
            }}
          >
            Mapas
          </Typography>
          <IconButton
            size="small"
            onClick={onClose}
            sx={{
              color: "#666",
              "&:hover": {
                backgroundColor: "rgba(0, 0, 0, 0.04)",
              },
            }}
          >
            <CloseIcon fontSize="small" />
          </IconButton>
        </Box>

        {/* Lista de mapas */}
        <List sx={{ padding: "4px 0" }}>
          {baseMaps.map((map) => {
            const isSelected = selectedMap?.id === map.id;
            return (
              <ListItem key={map.id} disablePadding>
                <ListItemButton
                  onClick={() => handleSelect(map)}
                  selected={isSelected}
                  sx={{
                    padding: "10px 16px",
                    "&.Mui-selected": {
                      backgroundColor: "rgba(74, 144, 226, 0.08)",
                      "&:hover": {
                        backgroundColor: "rgba(74, 144, 226, 0.12)",
                      },
                    },
                    "&:hover": {
                      backgroundColor: "rgba(0, 0, 0, 0.04)",
                    },
                  }}
                >
                  {map.image && (
                    <Box
                      component="img"
                      src={map.image}
                      alt={map.name}
                      sx={{
                        width: 50,
                        height: 40,
                        borderRadius: "4px",
                        marginRight: 2,
                        objectFit: "cover",
                        border: "1px solid rgba(0, 0, 0, 0.1)",
                      }}
                    />
                  )}
                  <ListItemText
                    primary={map.name}
                    primaryTypographyProps={{
                      fontSize: "13px",
                      fontWeight: isSelected ? 600 : 400,
                      color: isSelected ? "#4A90E2" : "#212121",
                    }}
                  />
                  {isSelected && (
                    <CheckIcon
                      sx={{
                        fontSize: "18px",
                        color: "#4A90E2",
                        marginLeft: 1,
                      }}
                    />
                  )}
                </ListItemButton>
              </ListItem>
            );
          })}
        </List>
      </Paper>
    </Collapse>
  );
}
