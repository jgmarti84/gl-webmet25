import { useEffect, useRef } from "react";

/**
 * Hook para sincronizar dos mapas en modo lock
 *
 * @param {Object} map1 - Instancia del primer mapa Leaflet
 * @param {Object} map2 - Instancia del segundo mapa Leaflet
 * @param {boolean} locked - Si los mapas deben estar sincronizados
 * @param {number} currentIndex1 - Índice de animación del mapa 1
 * @param {number} currentIndex2 - Índice de animación del mapa 2
 * @param {Function} setCurrentIndex2 - Setter para el índice del mapa 2
 */
export function useSplitScreenSync(
  map1,
  map2,
  locked,
  currentIndex1,
  currentIndex2,
  setCurrentIndex2
) {
  const syncingRef = useRef(false);

  // Sincronizar posición y zoom cuando se activa el lock
  useEffect(() => {
    if (!locked || !map1 || !map2) return;

    // Al activar lock, igualar el mapa 2 al mapa 1
    try {
      // Forzar recalculo de dimensiones del mapa antes de sincronizar
      map1.invalidateSize({ animate: false });
      map2.invalidateSize({ animate: false });

      // Pequeño delay para asegurar que invalidateSize se aplicó
      setTimeout(() => {
        const center1 = map1.getCenter();
        const zoom1 = map1.getZoom();

        syncingRef.current = true;
        map2.setView(center1, zoom1, { animate: false });
        syncingRef.current = false;
      }, 50);
    } catch (error) {
      console.error("Error al sincronizar vista inicial:", error);
    }
  }, [locked, map1, map2]);

  // Sincronizar movimientos y zoom mientras está locked
  useEffect(() => {
    if (!locked || !map1 || !map2) return;

    const syncMap1ToMap2 = () => {
      if (syncingRef.current) return;
      try {
        syncingRef.current = true;
        const center = map1.getCenter();
        const zoom = map1.getZoom();
        map2.setView(center, zoom, { animate: false });
        syncingRef.current = false;
      } catch (error) {
        console.error("Error al sincronizar mapa 1 -> 2:", error);
        syncingRef.current = false;
      }
    };

    const syncMap2ToMap1 = () => {
      if (syncingRef.current) return;
      try {
        syncingRef.current = true;
        const center = map2.getCenter();
        const zoom = map2.getZoom();
        map1.setView(center, zoom, { animate: false });
        syncingRef.current = false;
      } catch (error) {
        console.error("Error al sincronizar mapa 2 -> 1:", error);
        syncingRef.current = false;
      }
    };

    // Escuchar eventos de ambos mapas
    map1.on("move", syncMap1ToMap2);
    map1.on("zoom", syncMap1ToMap2);
    map2.on("move", syncMap2ToMap1);
    map2.on("zoom", syncMap2ToMap1);

    return () => {
      map1.off("move", syncMap1ToMap2);
      map1.off("zoom", syncMap1ToMap2);
      map2.off("move", syncMap2ToMap1);
      map2.off("zoom", syncMap2ToMap1);
    };
  }, [locked, map1, map2]);

  // Sincronizar índice de animación
  useEffect(() => {
    if (!locked) return;
    if (currentIndex1 !== currentIndex2) {
      setCurrentIndex2(currentIndex1);
    }
  }, [locked, currentIndex1, currentIndex2, setCurrentIndex2]);
}
