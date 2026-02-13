import { Snackbar, Alert } from "@mui/material";

export default function Alerts({ message, severity, open, onClose }) {
  return (
    <Snackbar
      open={open}
      autoHideDuration={6000}
      onClose={onClose}
      anchorOrigin={{ vertical: "top", horizontal: "center" }}
      sx={{ mt: 2 }}
    >
      <Alert
        onClose={onClose}
        severity={severity}
        sx={{ width: "100%", whiteSpace: "pre-line" }}
      >
        {message}
      </Alert>
    </Snackbar>
  );
}
