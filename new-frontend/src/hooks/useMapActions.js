import { useState, useCallback, useEffect } from "react";
import domtoimage from "dom-to-image-more";

/**
 * Custom hook para manejar acciones del mapa
 * - Captura de pantalla (usando dom-to-image-more para mejor calidad)
 * - Impresión
 * - Pantalla completa
 */
export function useMapActions() {
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Detectar cambios en fullscreen (por ESC u otros métodos)
  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };

    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => {
      document.removeEventListener("fullscreenchange", handleFullscreenChange);
    };
  }, []);

  /**
   * Espera a que todos los tiles del mapa se carguen
   * @param {HTMLElement} container - Contenedor del mapa
   * @param {number} timeout - Timeout en ms
   * @returns {Promise<void>}
   */
  const waitForTiles = useCallback((container, timeout = 3000) => {
    return new Promise((resolve) => {
      const startTime = Date.now();

      const checkTiles = () => {
        const tiles = container.querySelectorAll("img.leaflet-tile");
        const allLoaded = Array.from(tiles).every((tile) => tile.complete);

        if (allLoaded || Date.now() - startTime > timeout) {
          resolve();
        } else {
          setTimeout(checkTiles, 100);
        }
      };

      checkTiles();
    });
  }, []);

  /**
   * Captura una pantalla del mapa usando dom-to-image-more
   * Mejor manejo de CORS y tiles dinámicos que leaflet-image
   * @param {L.Map} mapRef - Referencia al mapa de Leaflet (no usado, mantenido por compatibilidad)
   * @param {string} containerId - ID del contenedor a capturar (default: "map-container")
   */
  const handleScreenshot = useCallback(
    async (mapRef, containerId = "map-container") => {
      try {
        const container = document.getElementById(containerId);
        if (!container) {
          console.error(`Contenedor "${containerId}" no encontrado`);
          return;
        }

        // Esperar a que los tiles se carguen
        await waitForTiles(container);

        // Ocultar temporalmente elementos no deseados
        const elementsToHide = container.querySelectorAll(
          ".no-print, .leaflet-control-zoom"
        );
        elementsToHide.forEach((el) => {
          el.dataset.originalDisplay = el.style.display;
          el.style.display = "none";
        });

        // Capturar con dom-to-image-more
        const dataUrl = await domtoimage.toPng(container, {
          quality: 1.0,
          bgcolor: "#ffffff",
          cacheBust: true,
          // Configuración CORS permisiva
          filter: (node) => {
            // Excluir controles y elementos no deseados
            if (node.classList) {
              return (
                !node.classList.contains("no-print") &&
                !node.classList.contains("leaflet-control-zoom")
              );
            }
            return true;
          },
        });

        // Restaurar elementos ocultos
        elementsToHide.forEach((el) => {
          el.style.display = el.dataset.originalDisplay || "";
          delete el.dataset.originalDisplay;
        });

        // Crear enlace de descarga
        const link = document.createElement("a");
        const timestamp = new Date()
          .toISOString()
          .replace(/[:.]/g, "-")
          .replace("T", "_")
          .substring(0, 19); // YYYY-MM-DD_HH-MM-SS
        link.download = `radar-map_${timestamp}.png`;
        link.href = dataUrl;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      } catch (error) {
        console.error("Error capturando pantalla:", error);
        throw error;
      }
    },
    [waitForTiles]
  );

  /**
   * Imprime el contenido del mapa
   */
  const handlePrint = useCallback(() => {
    try {
      window.print();
    } catch (error) {
      console.error("Error al imprimir:", error);
      throw error;
    }
  }, []);

  /**
   * Alterna el modo pantalla completa
   */
  const handleFullscreen = useCallback(async () => {
    try {
      if (!document.fullscreenElement) {
        // Entrar en pantalla completa
        await document.documentElement.requestFullscreen();
        setIsFullscreen(true);
      } else {
        // Salir de pantalla completa
        await document.exitFullscreen();
        setIsFullscreen(false);
      }
    } catch (error) {
      console.error("Error al cambiar pantalla completa:", error);
      throw error;
    }
  }, []);

  return {
    isFullscreen,
    handleScreenshot,
    handlePrint,
    handleFullscreen,
  };
}
