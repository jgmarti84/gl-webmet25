import { useCallback } from "react";

/**
 * Custom hook para gestionar descargas de archivos
 * Proporciona funcionalidades para descargar diferentes tipos de contenido:
 * - Imágenes desde URLs
 * - Imágenes desde canvas
 * - Datos JSON
 * - Archivos de texto
 * - COGs/GeoTIFFs desde backend
 */
export function useDownloads() {
  /**
   * Descarga una imagen desde una URL
   * @param {string} imageUrl - URL de la imagen (puede ser data URL o HTTP URL)
   * @param {string} filename - Nombre del archivo de descarga
   */
  const downloadImage = useCallback(async (imageUrl, filename) => {
    try {
      if (!imageUrl) {
        throw new Error("No hay URL de imagen");
      }

      // Si es una data URL, descargar directamente
      if (imageUrl.startsWith("data:")) {
        const link = document.createElement("a");
        link.href = imageUrl;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        return;
      }

      // Si es una URL HTTP, fetch y convertir a blob
      const response = await fetch(imageUrl);
      if (!response.ok) {
        throw new Error(`Error HTTP: ${response.status}`);
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Error descargando imagen:", error);
      throw error;
    }
  }, []);

  /**
   * Descarga un canvas como imagen PNG
   * @param {HTMLCanvasElement} canvas - Elemento canvas a descargar
   * @param {string} filename - Nombre del archivo de descarga
   */
  const downloadCanvas = useCallback((canvas, filename) => {
    try {
      if (!canvas || !(canvas instanceof HTMLCanvasElement)) {
        throw new Error("Canvas inválido");
      }

      canvas.toBlob((blob) => {
        if (!blob) {
          throw new Error("Error convirtiendo canvas a blob");
        }

        const url = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
      }, "image/png");
    } catch (error) {
      console.error("Error descargando canvas:", error);
      throw error;
    }
  }, []);

  /**
   * Descarga datos JSON como archivo
   * @param {Object} data - Datos a serializar
   * @param {string} filename - Nombre del archivo de descarga
   */
  const downloadJSON = useCallback((data, filename) => {
    try {
      const jsonString = JSON.stringify(data, null, 2);
      const blob = new Blob([jsonString], { type: "application/json" });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Error descargando JSON:", error);
      throw error;
    }
  }, []);

  /**
   * Descarga texto como archivo
   * @param {string} text - Contenido de texto
   * @param {string} filename - Nombre del archivo de descarga
   * @param {string} mimeType - Tipo MIME del archivo
   */
  const downloadText = useCallback(
    (text, filename, mimeType = "text/plain") => {
      try {
        const blob = new Blob([text], { type: mimeType });
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
      } catch (error) {
        console.error("Error descargando texto:", error);
        throw error;
      }
    },
    []
  );

  /**
   * Descarga un archivo desde el backend
   * @param {string} fileUrl - URL del archivo en el backend
   * @param {string} filename - Nombre del archivo de descarga
   */
  const downloadFile = useCallback(async (fileUrl, filename) => {
    try {
      const response = await fetch(fileUrl);
      if (!response.ok) {
        throw new Error(`Error HTTP: ${response.status}`);
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.style.display = "none";
      document.body.appendChild(link);
      link.click();

      // Esperar un poco antes de limpiar para que el navegador procese el click
      await new Promise((resolve) => setTimeout(resolve, 100));

      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Error descargando archivo:", error);
      throw error;
    }
  }, []);

  /**
   * Genera un nombre de archivo con timestamp
   * @param {string} prefix - Prefijo del nombre
   * @param {string} extension - Extensión del archivo (con punto)
   * @returns {string} Nombre de archivo con timestamp
   */
  const generateFilename = useCallback((prefix, extension) => {
    const timestamp = new Date()
      .toISOString()
      .replace(/[:.]/g, "-")
      .replace("T", "_")
      .substring(0, 19); // YYYY-MM-DD_HH-MM-SS
    return `${prefix}_${timestamp}${extension}`;
  }, []);

  return {
    downloadImage,
    downloadCanvas,
    downloadJSON,
    downloadText,
    downloadFile,
    generateFilename,
  };
}
