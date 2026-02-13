import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000",
});

export const uploadFile = async (files, session_id = null) => {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  if (session_id) {
    formData.append("session_id", session_id);
  }
  return api.post("/upload", formData);
};

export const processFile = async ({
  files,
  layers,
  product,
  height,
  elevation,
  filters,
  selectedVolumes,
  selectedRadars,
  colormap_overrides,
  session_id,
}) => {
  const payload = {
    filepaths: files,
    product: product,
    fields: layers,
    ...(height !== null &&
      height !== undefined && { height: parseInt(height) }),
    ...(elevation !== undefined &&
      elevation !== null && { elevation: parseInt(elevation) }),
    ...(filters && { filters }),
    ...(selectedVolumes && { selectedVolumes }),
    ...(selectedRadars && { selectedRadars }),
    ...(colormap_overrides && { colormap_overrides }),
    ...(session_id && { session_id }),
  };

  return api.post("/process", payload);
};

export function cleanupClose(payload) {
  // payload: { uploads: string[], cogs: string[], delete_cache: boolean, session_id?: string }
  return api.post("/cleanup/close", payload, {
    headers: { "Content-Type": "application/json" },
  });
}

export async function generatePseudoRHI({
  filepath,
  field,
  end_lon,
  end_lat,
  start_lon,
  start_lat,
  max_length_km,
  max_height_km,
  elevation = 0,
  filters = [],
  png_width_px = 900,
  png_height_px = 500,
  colormap_overrides,
  session_id,
}) {
  return api.post("/process/pseudo_rhi", {
    filepaths: [filepath],
    field,
    end_lon,
    end_lat,
    ...(start_lon != null &&
      start_lat != null && {
        start_lon,
        start_lat,
      }),
    max_length_km: max_length_km,
    max_height_km: max_height_km,
    elevation,
    filters,
    png_width_px,
    png_height_px,
    ...(colormap_overrides && { colormap_overrides }),
    ...(session_id && { session_id }),
  });
}

export async function generateAreaStats(payload) {
  const {
    polygon,
    filepath,
    product,
    field,
    height,
    elevation,
    filters,
    session_id,
  } = payload;

  return api.post("/stats/area", {
    polygon_geojson: polygon,
    filepath,
    product,
    field,
    ...(height !== null &&
      height !== undefined && { height: parseInt(height) }),
    ...(elevation !== undefined &&
      elevation !== null && { elevation: parseInt(elevation) }),
    ...(filters && { filters }),
    ...(session_id && { session_id }),
  });
}

export async function generatePixelStat(payload) {
  const {
    filepath,
    product,
    field,
    height,
    elevation,
    filters,
    lat,
    lon,
    session_id,
  } = payload;

  return api.post("/stats/pixel", {
    filepath,
    product,
    field,
    ...(height !== null &&
      height !== undefined && { height: parseInt(height) }),
    ...(elevation !== undefined &&
      elevation !== null && { elevation: parseInt(elevation) }),
    ...(filters && { filters }),
    lat,
    lon,
    ...(session_id && { session_id }),
  });
}

export async function generateElevationProfile({
  coordinates,
  interpolate = true,
  points_per_km = 10,
}) {
  return api.post("/stats/elevation_profile", {
    coordinates,
    interpolate,
    points_per_km,
  });
}

export async function getColormapOptions() {
  const response = await api.get("/colormap/options");
  return response.data;
}

export async function getColormapDefaults() {
  const response = await api.get("/colormap/defaults");
  return response.data;
}

export async function getCacheStats() {
  const response = await api.get("/admin/cache-stats");
  return response.data;
}

export async function clearCache(cacheType = "all") {
  const response = await api.post(`/admin/clear-cache?cache_type=${cacheType}`);
  return response.data;
}
