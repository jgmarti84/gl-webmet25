import { cleanupClose } from "../api/backend";

export function registerCleanupAxios(getPayload) {
  const url = `http://localhost:8000/cleanup/close`;

  const handler = () => {
    try {
      const payload = getPayload?.();
      if (!payload) return;

      // 1) Preferir sendBeacon (fiable en unload)
      const blob = new Blob([JSON.stringify(payload)], {
        type: "application/json",
      });
      if (navigator.sendBeacon && navigator.sendBeacon(url, blob)) return;

      // 2) Fallback: axios (puede cortarse si el navegador cierra muy rápido)
      // No await: fire-and-forget
      cleanupClose(payload).catch(() => {});
    } catch {
      /* ignore */
    }
  };

  // cubrir más casos de cierre
  window.addEventListener("pagehide", handler);
  window.addEventListener("beforeunload", handler);

  return () => {
    window.removeEventListener("pagehide", handler);
    window.removeEventListener("beforeunload", handler);
  };
}

// toma outputs = overlayData.outputs y devuelve rutas en FS para borrar
export function cogFsPaths(outputs) {
  return (outputs || [])
    .map((o) => o?.image_url) // "static/tmp/radar_...tif"
    .filter(Boolean)
    .map((rel) => {
      // convertir URL estática a ruta de FS
      const file = rel.replace(/^static\/tmp\//, "");
      return `app/storage/tmp/${file}`; // ruta que el server puede borrar
    });
}
