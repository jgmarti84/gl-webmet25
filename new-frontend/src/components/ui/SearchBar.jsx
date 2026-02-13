import { useState } from "react";
import {
  Paper,
  InputBase,
  IconButton,
  List,
  ListItem,
  ListItemText,
  Collapse,
} from "@mui/material";
import SearchIcon from "@mui/icons-material/Search";
import CloseIcon from "@mui/icons-material/Close";

export default function SearchBar({ map, onSearch }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [expanded, setExpanded] = useState(false);

  // Ubicaciones predefinidas de Argentina (ciudades principales)
  const locations = [
    { name: "Córdoba", lat: -31.4201, lon: -64.1888 },
    { name: "Buenos Aires", lat: -34.6037, lon: -58.3816 },
    { name: "Rosario", lat: -32.9442, lon: -60.6505 },
    { name: "Mendoza", lat: -32.8895, lon: -68.8458 },
    { name: "Tucumán", lat: -26.8241, lon: -65.2226 },
    { name: "Salta", lat: -24.7821, lon: -65.4232 },
    { name: "Mar del Plata", lat: -38.0055, lon: -57.5426 },
    { name: "Paraná", lat: -31.7333, lon: -60.5297 },
    { name: "Neuquén", lat: -38.9516, lon: -68.0591 },
    { name: "Resistencia", lat: -27.4514, lon: -58.9867 },
  ];

  const handleSearch = (searchQuery) => {
    if (!searchQuery || searchQuery.length < 2) {
      setResults([]);
      setExpanded(false);
      return;
    }

    const filtered = locations.filter((loc) =>
      loc.name.toLowerCase().includes(searchQuery.toLowerCase())
    );
    setResults(filtered);
    setExpanded(filtered.length > 0);
  };

  const handleInputChange = (e) => {
    const value = e.target.value;
    setQuery(value);
    handleSearch(value);
  };

  const handleSelectLocation = (location) => {
    if (map) {
      map.setView([location.lat, location.lon], 9);
    }
    setQuery(location.name);
    setResults([]);
    setExpanded(false);

    if (onSearch) {
      onSearch(location);
    }
  };

  const handleClear = () => {
    setQuery("");
    setResults([]);
    setExpanded(false);
  };

  return (
    <Paper
      elevation={3}
      sx={{
        position: "absolute",
        top: 16,
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 1000,
        display: "flex",
        flexDirection: "column",
        backgroundColor: "rgba(255, 255, 255, 0.98)",
        backdropFilter: "blur(8px)",
        borderRadius: "8px",
        boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
        minWidth: 300,
        maxWidth: 400,
      }}
    >
      {/* Barra de búsqueda */}
      <div
        style={{ display: "flex", alignItems: "center", padding: "8px 12px" }}
      >
        <SearchIcon sx={{ color: "#666", marginRight: 1 }} />
        <InputBase
          placeholder="Buscar localidad..."
          value={query}
          onChange={handleInputChange}
          sx={{
            flex: 1,
            fontSize: "14px",
            color: "#212121",
            "& input::placeholder": {
              color: "#999",
              opacity: 1,
            },
          }}
        />
        {query && (
          <IconButton size="small" onClick={handleClear}>
            <CloseIcon fontSize="small" />
          </IconButton>
        )}
      </div>

      {/* Resultados */}
      <Collapse in={expanded}>
        <List sx={{ padding: 0, maxHeight: 250, overflow: "auto" }}>
          {results.map((location, index) => (
            <ListItem
              key={index}
              button
              onClick={() => handleSelectLocation(location)}
              sx={{
                padding: "10px 16px",
                "&:hover": {
                  backgroundColor: "rgba(25, 118, 210, 0.08)",
                },
                borderTop: index > 0 ? "1px solid rgba(0,0,0,0.08)" : "none",
              }}
            >
              <ListItemText
                primary={location.name}
                primaryTypographyProps={{
                  fontSize: "14px",
                  fontWeight: 500,
                }}
                secondary={`${location.lat.toFixed(4)}, ${location.lon.toFixed(
                  4
                )}`}
                secondaryTypographyProps={{
                  fontSize: "12px",
                  color: "#666",
                }}
              />
            </ListItem>
          ))}
        </List>
      </Collapse>
    </Paper>
  );
}
