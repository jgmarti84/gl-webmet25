import { useEffect, useState } from "react";
import {
  Box,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Paper,
  Typography,
  IconButton,
  Button,
  Collapse,
  Divider,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import CheckIcon from "@mui/icons-material/Check";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import { getColormapOptions, getColormapDefaults } from "../../api/backend";

export default function ColorPaletteSelector({
  open,
  onClose,
  selectedColormaps,
  onSelectColormap,
  availableFields,
  onApply,
  hasLoadedImages,
  initialColormaps,
}) {
  const [colormapOptions, setColormapOptions] = useState({});
  const [defaultColormaps, setDefaultColormaps] = useState({});
  const [loading, setLoading] = useState(true);

  // Detectar si hubo cambios respecto a las paletas iniciales
  const hasChanges = () => {
    if (!initialColormaps || Object.keys(initialColormaps).length === 0) {
      return Object.keys(selectedColormaps).length > 0;
    }
    return (
      JSON.stringify(selectedColormaps) !== JSON.stringify(initialColormaps)
    );
  };

  const handleApply = () => {
    if (onApply) {
      onApply();
    }
    onClose();
  };

  useEffect(() => {
    const fetchOptions = async () => {
      try {
        const [options, defaults] = await Promise.all([
          getColormapOptions(),
          getColormapDefaults(),
        ]);
        setColormapOptions(options);
        setDefaultColormaps(defaults);
      } catch (error) {
        console.error("Error fetching colormap options:", error);
      } finally {
        setLoading(false);
      }
    };

    if (open) {
      fetchOptions();
    }
  }, [open]);

  const handleSelect = (field, colormap) => {
    onSelectColormap(field, colormap);
  };

  // Función para mostrar nombre amigable del colormap
  const getColormapDisplayName = (cmapKey) => {
    // Remover prefijos y hacer más legible
    let displayName = cmapKey
      .replace("grc_", "GRC ")
      .replace("pyart_", "PyART ")
      .replace("_", " ");

    // Capitalizar primera letra
    return displayName.charAt(0).toUpperCase() + displayName.slice(1);
  };

  if (loading) {
    return null;
  }

  // Filtrar solo los campos disponibles
  const fieldsToShow =
    availableFields?.length > 0
      ? availableFields.filter((field) => colormapOptions[field])
      : Object.keys(colormapOptions);

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
          left: 68,
          zIndex: 999,
          width: 320,
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
            position: "sticky",
            top: 0,
            backgroundColor: "rgba(255, 255, 255, 0.98)",
            zIndex: 1,
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
            Paletas de Colores
          </Typography>
          <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
            {hasChanges() && hasLoadedImages && (
              <Button
                size="small"
                variant="contained"
                startIcon={<CheckCircleIcon />}
                onClick={handleApply}
                sx={{
                  fontSize: "12px",
                  textTransform: "none",
                  backgroundColor: "#4A90E2",
                  "&:hover": {
                    backgroundColor: "#357ABD",
                  },
                }}
              >
                Aplicar
              </Button>
            )}
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
        </Box>

        {/* Lista por campo */}
        {fieldsToShow.length === 0 ? (
          <Box sx={{ padding: "20px", textAlign: "center" }}>
            <Typography variant="body2" color="text.secondary">
              No hay campos disponibles
            </Typography>
          </Box>
        ) : (
          fieldsToShow.map((field) => {
            const options = colormapOptions[field] || [];
            const currentSelection =
              selectedColormaps[field] || defaultColormaps[field];

            return (
              <Box key={field}>
                <Box
                  sx={{
                    padding: "8px 16px",
                    backgroundColor: "rgba(74, 144, 226, 0.05)",
                  }}
                >
                  <Typography
                    variant="caption"
                    sx={{
                      fontWeight: 600,
                      fontSize: "11px",
                      color: "#4A90E2",
                      textTransform: "uppercase",
                      letterSpacing: "0.5px",
                    }}
                  >
                    {field}
                  </Typography>
                </Box>
                <List sx={{ padding: "4px 0" }}>
                  {options.map((colormap) => {
                    const isSelected = currentSelection === colormap;
                    const isDefault = defaultColormaps[field] === colormap;

                    return (
                      <ListItem key={`${field}-${colormap}`} disablePadding>
                        <ListItemButton
                          onClick={() => handleSelect(field, colormap)}
                          selected={isSelected}
                          sx={{
                            padding: "8px 16px 8px 24px",
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
                          <ListItemText
                            primary={
                              <Box
                                sx={{
                                  display: "flex",
                                  alignItems: "center",
                                  gap: 1,
                                }}
                              >
                                <span>{getColormapDisplayName(colormap)}</span>
                                {isDefault && (
                                  <Typography
                                    component="span"
                                    sx={{
                                      fontSize: "10px",
                                      color: "#999",
                                      fontStyle: "italic",
                                    }}
                                  >
                                    (default)
                                  </Typography>
                                )}
                              </Box>
                            }
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
                <Divider />
              </Box>
            );
          })
        )}
      </Paper>
    </Collapse>
  );
}
