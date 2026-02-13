import { Marker, Polyline, useMapEvent } from "react-leaflet";

export default function MapPickOverlay({
  enabled,
  pickedPoint,
  onPick,
}) {
  useMapEvent("click", (e) => {
    if (!enabled) return;
    onPick?.({ lat: e.latlng.lat, lon: e.latlng.lng });
  });

  if (!enabled && !pickedPoint) return null;

  const pp = pickedPoint ? [pickedPoint.lat, pickedPoint.lon] : null;

  return (
    <>
      {pp && <Marker position={pp} />}
    </>
  );
}
