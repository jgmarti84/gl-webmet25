import { Box, Button, Paper } from "@mui/material";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import logoSrc from "../../assets/lrsr_logo.png";

export default function HeaderCard({ onUploadClick }) {
  return (
    <Paper
      elevation={3}
      sx={{
        position: "absolute",
        top: 12,
        left: 14,
        zIndex: 1000,
        display: "flex",
        alignItems: "center",
        gap: 6,
        padding: "8px 14px",
        backgroundColor: "rgba(74, 144, 226, 0.95)",
        backdropFilter: "blur(8px)",
        borderRadius: "8px",
        boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
      }}
    >
      {/* Logo */}
      <Box
        component="img"
        src={logoSrc}
        alt="LRSR Logo"
        sx={{
          height: 36,
          width: "auto",
          objectFit: "contain",
          marginLeft: 1,
        }}
        onError={(e) => {
          // Fallback si la imagen no carga
          e.target.style.display = "none";
        }}
      />

      {/* Botón de upload */}
      <Button
        variant="contained"
        startIcon={<CloudUploadIcon />}
        onClick={onUploadClick}
        sx={{
          backgroundColor: "rgba(255, 255, 255, 0.25)",
          color: "white",
          textTransform: "none",
          fontWeight: 500,
          fontSize: "12px",
          padding: "7px 14px",
          borderRadius: "6px",
          boxShadow: "none",
          border: "1px solid rgba(255, 255, 255, 0.3)",
          "&:hover": {
            backgroundColor: "rgba(255, 255, 255, 0.35)",
            boxShadow: "none",
            border: "1px solid rgba(255, 255, 255, 0.5)",
          },
        }}
      >
        Subir archivos
      </Button>
    </Paper>
  );
}
