import { Box, IconButton, Paper } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import RemoveIcon from "@mui/icons-material/Remove";
import MyLocationIcon from "@mui/icons-material/MyLocation";

export default function ZoomControls({ map }) {
  const handleZoomIn = () => {
    if (map) {
      map.zoomIn();
    }
  };

  const handleZoomOut = () => {
    if (map) {
      map.zoomOut();
    }
  };

  const handleResetView = () => {
    if (map) {
      map.setView([-31.4, -64.2], 6); // Centro de Argentina aproximado
    }
  };

  return (
    <Paper
      elevation={0}
      sx={{
        position: "absolute",
        bottom: 22,
        right: 12,
        zIndex: 1000,
        display: "flex",
        flexDirection: "column",
        backgroundColor: "rgba(255, 255, 255, 0.98)",
        backdropFilter: "blur(8px)",
        borderRadius: "8px",
        boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
        padding: "4px",
      }}
    >
      {/* Zoom In */}
      <IconButton
        onClick={handleZoomIn}
        sx={{
          width: 18,
          height: 18,
          borderRadius: "6px",
          margin: "2px",
          color: "#666",
          transition: "all 0.2s ease",
          border: "0px solid transparent",
          boxShadow: "none",
          "&:hover": {
            backgroundColor: "rgba(25, 118, 210, 0.08)",
            color: "#1976d2",
          },
        }}
      >
        <AddIcon fontSize="small" />
      </IconButton>

      {/* Divider */}
      <Box
        sx={{
          height: "1px",
          backgroundColor: "rgba(0, 0, 0, 0.08)",
          margin: "2px 8px",
        }}
      />

      {/* Zoom Out */}
      <IconButton
        onClick={handleZoomOut}
        sx={{
          width: 18,
          height: 18,
          borderRadius: "6px",
          margin: "2px",
          color: "#666",
          transition: "all 0.2s ease",
          border: "0px solid transparent",
          boxShadow: "none",
          "&:hover": {
            backgroundColor: "rgba(25, 118, 210, 0.08)",
            color: "#1976d2",
          },
        }}
      >
        <RemoveIcon fontSize="small" />
      </IconButton>

      {/* Divider */}
      <Box
        sx={{
          height: "1px",
          backgroundColor: "rgba(0, 0, 0, 0.08)",
          margin: "2px 8px",
        }}
      />

      {/* Reset View / Home */}
      <IconButton
        onClick={handleResetView}
        sx={{
          width: 18,
          height: 18,
          borderRadius: "6px",
          margin: "2px",
          color: "#666",
          transition: "all 0.2s ease",
          border: "0px solid transparent",
          boxShadow: "none",
          "&:hover": {
            backgroundColor: "rgba(25, 118, 210, 0.08)",
            color: "#1976d2",
          },
        }}
      >
        <MyLocationIcon fontSize="small" />
      </IconButton>
    </Paper>
  );
}
