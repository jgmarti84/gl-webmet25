import React, { useState } from "react";
import { Paper, Typography, IconButton } from "@mui/material";
import DragIndicatorIcon from "@mui/icons-material/DragIndicator";
import CloseIcon from "@mui/icons-material/Close";

export default function WarningPanel({ warnings = [] }) {
  const [visible, setVisible] = useState(true);
  const [pos, setPos] = useState({ x: 30, y: 80 });
  const [dragging, setDragging] = useState(false);
  const [offset, setOffset] = useState({ x: 0, y: 0 });

  if (!visible || !warnings.length) return null;

  const handleMouseDown = (e) => {
    setDragging(true);
    setOffset({ x: e.clientX - pos.x, y: e.clientY - pos.y });
  };
  const handleMouseMove = (e) => {
    if (!dragging) return;
    setPos({ x: e.clientX - offset.x, y: e.clientY - offset.y });
  };
  const handleMouseUp = () => setDragging(false);

  return (
    <Paper
      elevation={6}
      sx={{
        position: "fixed",
        top: pos.y,
        left: pos.x,
        zIndex: 9999,
        width: 360,
        maxHeight: 300,
        overflowY: "auto",
        cursor: dragging ? "grabbing" : "default",
        bgcolor: "#fff7e6",
        border: "1px solid #fbc02d",
        p: 1,
      }}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          cursor: "grab",
          alignItems: "center",
        }}
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
      >
        <Typography
          variant="subtitle2"
          sx={{ color: "#ff8f00", fontWeight: 600 }}
        >
          Warnings
        </Typography>
        <div>
          <IconButton size="small" onClick={() => setVisible(false)}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </div>
      </div>

      {warnings.map((w, i) => (
        <Typography key={i} variant="body2" sx={{ mt: 0.5, color: "#444" }}>
          {w}
        </Typography>
      ))}
    </Paper>
  );
}
