import { useState } from "react";
import { Box, Paper, Typography } from "@mui/material";
import {
    AreaChart,
    Line,
    Area,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    ReferenceDot,
} from "recharts";

/**
 * Custom tooltip para mostrar información detallada al hacer hover
 */
function CustomTooltip({ active, payload }) {
    if (active && payload && payload.length) {
        const data = payload[0].payload;
        return (
            <Paper
                sx={{
                    padding: 1.5,
                    backgroundColor: "rgba(255, 255, 255, 0.95)",
                    border: "1px solid #ccc",
                }}
            >
                <Typography variant="body2" sx={{ fontWeight: "bold" }}>
                    Distancia: {data.distance.toFixed(2)} km
                </Typography>
                <Typography variant="body2" color="primary">
                    Altura: {data.elevation.toFixed(0)} m
                </Typography>
                <Typography variant="caption" color="textSecondary">
                    Lat: {data.lat.toFixed(4)}°, Lon: {data.lon.toFixed(4)}°
                </Typography>
            </Paper>
        );
    }
    return null;
}

/**
 * Componente reutilizable para mostrar el perfil de elevación
 * 
 * Props:
 * - profileData: Array de objetos { distance, elevation, lat, lon }
 * - height: Altura del gráfico en px (default: 250)
 * - onHover: (point | null) => void - callback cuando se hace hover
 * - onClick: () => void - callback cuando se hace click en el gráfico
 * - clickable: boolean - si el gráfico es clickable para expandir
 */
export default function ElevationChart({
    profileData = [],
    height = 250,
    onHover,
    onClick,
    clickable = false,
}) {
    const [hoveredPoint, setHoveredPoint] = useState(null);

    const handleMouseMove = (e) => {
        if (e && e.activePayload && e.activePayload.length > 0) {
            const point = e.activePayload[0].payload;
            setHoveredPoint(point);
            onHover?.(point);
        }
    };

    const handleMouseLeave = () => {
        setHoveredPoint(null);
        onHover?.(null);
    };

    const handleClick = () => {
        if (clickable && onClick) {
            onClick();
        }
    };

    if (!profileData || profileData.length === 0) {
        return (
            <Box
                sx={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    height: height,
                    backgroundColor: "#f5f5f5",
                    borderRadius: 2,
                }}
            >
                <Typography variant="body2" color="text.secondary">
                    No hay datos de elevación disponibles
                </Typography>
            </Box>
        );
    }

    return (
        <Box
            sx={{
                cursor: clickable ? "pointer" : "default",
                transition: "opacity 0.2s",
                "&:hover": clickable
                    ? {
                        opacity: 0.8,
                    }
                    : {},
            }}
            onClick={handleClick}
        >
            <ResponsiveContainer width="100%" height={height}>
                <AreaChart
                    data={profileData}
                    onMouseMove={handleMouseMove}
                    onMouseLeave={handleMouseLeave}
                    margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
                >
                    <defs>
                        <linearGradient
                            id="elevationGradient"
                            x1="0"
                            y1="0"
                            x2="0"
                            y2="1"
                        >
                            <stop offset="0%" stopColor="#ff6b35" stopOpacity={0.9} />
                            <stop offset="95%" stopColor="#ff6b35" stopOpacity={0.1} />
                        </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                        dataKey="distance"
                        label={{
                            value: "Distancia (km)",
                            position: "insideBottom",
                            offset: -5,
                        }}
                        interval="preserveStartEnd"
                        minTickGap={40}
                        tickFormatter={(value) => Math.round(value)}
                    />
                    <YAxis
                        label={{
                            value: "Altura (m)",
                            angle: -90,
                            position: "insideLeft",
                        }}
                        tickFormatter={(value) => value.toFixed(0)}
                    />
                    <Tooltip content={<CustomTooltip />} />
                    <Area
                        type="monotone"
                        dataKey="elevation"
                        stroke="none"
                        fill="url(#elevationGradient)"
                    />
                    <Line
                        type="monotone"
                        dataKey="elevation"
                        stroke="#ff6b35"
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 6 }}
                    />
                    {hoveredPoint && (
                        <ReferenceDot
                            x={hoveredPoint.distance}
                            y={hoveredPoint.elevation}
                            r={8}
                            fill="#ff0000"
                            stroke="#fff"
                            strokeWidth={2}
                        />
                    )}
                </AreaChart>
            </ResponsiveContainer>
        </Box>
    );
}
