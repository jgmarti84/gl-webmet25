import { MapContainer, TileLayer, ImageOverlay } from "react-leaflet";
import "leaflet/dist/leaflet.css";

export default function MapView({ overlayData }) {
  return (
    <MapContainer
      center={[-34.6, -58.4]}
      zoom={5}
      style={{ height: "100vh", width: "105%" }}
    >
      <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      {overlayData != null && (
        <ImageOverlay
          url={"http://localhost:8000/" + overlayData.image_url}
          bounds={overlayData.bounds}
          opacity={0.9}
        />
      )}
    </MapContainer>
  );
}
