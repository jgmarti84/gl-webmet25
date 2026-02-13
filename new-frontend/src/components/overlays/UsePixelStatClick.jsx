import { useEffect } from "react";
import { useMap } from "react-leaflet";

export default function UsePixelStatClick({ enabled, onPixelStatClick }) {
    const map = useMap();
    useEffect(() => {
        if (!enabled) return;

        const handler = (e) => onPixelStatClick?.(e.latlng);
        map.getContainer().style.cursor = "crosshair";
        map.on("click", handler);
        return () => {
            map.off("click", handler);
            map.getContainer().style.cursor = "";
        };
    }, [enabled, onPixelStatClick, map]);

    return null;
}