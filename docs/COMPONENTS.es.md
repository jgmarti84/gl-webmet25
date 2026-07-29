# COMPONENTS.md — Módulos del Frontend de WebMet25

> Versión en español de [COMPONENTS.md](COMPONENTS.md).

> **Propósito:** Documentar los componentes funcionales del frontend de WebMet25, sus responsabilidades y ubicaciones de archivos.

---

## Descripción general

El frontend de WebMet25 es una aplicación JavaScript modular construida con ES6 vanilla, Leaflet y basemaps de CartoDB. **No tiene herramienta de compilación, sin dependencias de frameworks ni biblioteca de gestión de estado** — todo el estado se gestiona en un objeto global `state` en `app.js`.

**Organización de archivos:**
```
frontend/public/
├── index.html                 # Main multi-radar map page
├── radar.html                 # One-radar detail page (radar.html?code=AR5)
├── admin.html                 # Admin panel SPA (served at /admin, Basic Auth)
├── css/
│   ├── styles.css            # Main app UI styling (dark theme)
│   └── admin.css             # Admin panel styling (modern-light theme)
└── js/
    ├── admin.js              # Admin panel orchestrator (CRUD, filters, colormap creator)
    ├── admin-api.js          # Admin REST client (/api/v1/admin/*)
    ├── shared/               # Shared by v1 and v2
    │   ├── api.js            # REST API client
    │   ├── controls.js       # UI control handlers (+ radar ordering, time-wheel wiring)
    │   ├── legend.js         # Legend renderer
    │   ├── tops-cores.js     # TopsCoresLayer (polígonos blob + marcadores SVG)
    │   ├── time-wheel.js     # iOS-style HH:MM scroll picker (custom time range)
    └── v2/                   # Current production frontend
        ├── app.js            # Main orchestrator & state management (multi-radar map)
        ├── radar-app.js      # One-radar page orchestrator & state management
        ├── map.js            # MapManager with L.imageOverlay (shared)
        ├── animation.js      # AnimationController with requestAnimationFrame (shared)
        ├── radar-utils.js    # Helpers: waitForLeaflet, updateRadarHeader, buildGridFrames…
        └── constants.js      # Shared constants: MS_PER_HOUR, DEFAULT_*, COVERAGE_MODES
```

> **v2 es el estándar de producción actual.** El directorio v1 se conserva como referencia.
> El **panel de administración** (`admin.html` + `admin.js` + `admin-api.js` + `admin.css`) es un SPA independiente — ver el componente *Panel de administración* más adelante.

---

## Componentes principales

### 1. **app.js** (v2) — Orquestador principal de la aplicación

**Archivo:** [`frontend/public/js/v2/app.js`](../../frontend/public/js/v2/app.js)

**Responsabilidad:** Orquestador central del frontend v2. Gestiona el estado global de la aplicación, inicializa todos los módulos, maneja la selección de radar/producto, el cambio de modo de cobertura, la continuidad de animación, la visibilidad de cimas y núcleos (tops & cores) y el sondeo de actualización en vivo.

**Exportaciones principales:**
- Objeto `state` — Estado global (radars, products, selectedRadars, selectedProduct, COGs, animator, mapManager, topsCoresLayer, ...)
- `init()` — Función de arranque llamada al cargar la página

**Estructura del estado (v2):**
```javascript
const state = {
    radars: [],
    products: [],
    cogs: [],
    selectedRadars: [],
    selectedProduct: null,
    showUnfilteredProducts: false,
    showInactiveRadars: false,
    activeTimeWindowHours: 1.5,   // default 90 min
    selectedColormap: null,
    currentVmin: null,
    currentVmax: null,
    fieldOpacity: {},             // per-radar opacity
    mapManager: null,
    animator: null,
    ui: null,
    legend: null,
    topsCoresLayer: null,
    topsCoresVisible: false,
    topsCoresPointSize: 8,
    animationMode: null,          // "live" | "replay" | null
    liveRefreshInterval: null,
    radarStatusRefreshInterval: null,
    // ... more
};
```

**Modos de cobertura (`COVERAGE_MODES` — definido en `v2/constants.js`):**
```javascript
const COVERAGE_MODES = [
    { id: 'cd',  label: 'C+D', volNrs: ['01', '02'], strategy: '0315', filteredFieldsAvailable: true,  defaultProduct: 'COLMAXo' },
    { id: 'vig', label: 'VIG', volNrs: ['04'],        strategy: '0315', filteredFieldsAvailable: false, defaultProduct: 'DBZHo'   },
];
```
El modo se persiste en la clave `webmet25_coverage_mode` de `localStorage`. Las consultas de COG pasan los `volNrs` del modo activo como parámetros `?vol_nr=`. El intervalo de actualización del estado del radar se persiste en `webmet25_radar_refresh_interval_min` (por defecto 10).

**Dependencias:** `shared/api.js`, `v2/map.js`, `v2/animation.js`, `shared/controls.js`, `shared/legend.js`, `shared/tops-cores.js`

---

### 2. **api.js** — Cliente REST de la API

**Archivo:** [`frontend/public/js/shared/api.js`](../../frontend/public/js/shared/api.js)

**Responsabilidad:** Encapsula toda la comunicación HTTP con la API del backend. Provee funciones para obtener radares, productos, metadatos de COG, datos de colormap y maneja respuestas de error. Es la única fuente de verdad para la URL base de la API.

**Funciones principales:**

```text
getRadars() -> GET /api/v1/radars
getProducts() -> GET /api/v1/products
getCogs(radarCode, productKey, startTime, endTime, strategy?, volNrs?)
   -> GET /api/v1/cogs?...
   (soporta strategy y vol_nr repetible para el modo de cobertura)
getColormapInfo(productKey) -> GET /api/v1/products/{key}/colormap
getFrameUrl(cogId, params) -> construye /frames/{id}/image.png con query params
getTopsAndCores(radarCodes, timeFrom, timeTo) -> GET /api/v1/tops-cores
getTopsAndCoresFeatures(id) -> GET /api/v1/tops-cores/{id}/features
```

**Dependencias:** Ninguna (cliente HTTP independiente)

**Manejo de errores:** Todas las funciones capturan errores y lanzan excepciones descriptivas; el llamador debe manejarlas con try/catch

---

### 3. **map.js** (v2) — Gestor del mapa Leaflet

**Archivo:** [`frontend/public/js/v2/map.js`](../../frontend/public/js/v2/map.js)

**Responsabilidad:** Envuelve el mapa Leaflet con renderizado de radar basado en `L.imageOverlay`. Gestiona la carga de fotogramas desde `/frames/{id}/image.png`, su visualización como overlays geo-referenciados, el cambio de basemap, la máscara de cobertura (SVG) y el control de opacidad.

**Métodos principales:**

```text
init(containerId) — Crea el mapa con la vista inicial
setBasemap(key) — Cambia entre OSM, IGN y otros basemaps
loadFrames(cogsByFrame) — Pre-carga imágenes y las guarda como L.imageOverlay
showFrame(index) — Muestra el fotograma en el índice indicado
setOpacity(radarCode, opacity) — Ajusta la opacidad del overlay del radar
addRadarCoverage(code, lat, lng, radius_m) — Agrega un círculo SVG a la máscara
removeRadarCoverage(code) — Elimina el círculo de cobertura
updateParams(newParams) — Recarga en segundo plano con intercambio atómico
```

**Estado interno:** Mapa `_frameImages` interno, `_overlays` por radar, SVG `_coverageMask`

---

### 3b. **Suavizado gaussiano** — Filtro de imagen del lado del servidor

**Implementado en:** [`api/app/services/smoothing.py`](../../api/app/services/smoothing.py)  
**Expuesto mediante:** `/frames/{cog_id}/image.png?smooth=true&smooth_sigma=0.8`

**Responsabilidad:** Aplica un desenfoque gaussiano (`scipy.ndimage.gaussian_filter`) al array de datos float crudos *antes* de aplicar el colormap, generando imágenes de radar visualmente más suaves. Se ejecuta en el servidor, en el hilo de renderizado.

**Claves de localStorage:** `webmet25_smooth_enabled` (booleano, por defecto `false`) · `webmet25_smooth_sigma` (número, por defecto `0.8`)

**Parámetros:**

| Parámetro | Tipo | Por defecto | Descripción |
|-----------|------|-------------|-------------|
| `smooth` | bool | false | Activa/desactiva el suavizado gaussiano |
| `smooth_sigma` | float | 0.8 | Desviación estándar del kernel gaussiano (píxeles). Mayor valor = mayor desenfoque |

**Comportamiento:**
- Se aplica después del enmascaramiento de datos y antes de la búsqueda en el colormap — el suavizado opera sobre valores float, no sobre píxeles RGBA
- Cuando `smooth=false`, el parámetro `smooth_sigma` se ignora y no afecta a las claves de caché
- La clave de caché incluye `(smooth, smooth_sigma)` solo cuando `smooth=true`, por lo que las solicitudes sin suavizado siempre comparten la misma clave independientemente del valor sigma enviado

**Integración con el frontend:** Los valores `smooth` y `smooth_sigma` se añaden a la URL `/frames/{id}/image.png` construida por `shared/api.js`. El panel de configuración en v2 expone un toggle de suavizado y un deslizador de sigma.

---

### 4. **animation.js** (v2) — Controlador de animación de fotogramas

**Archivo:** [`frontend/public/js/v2/animation.js`](../../frontend/public/js/v2/animation.js)

**Responsabilidad:** Gestiona la reproducción de secuencias de fotogramas del radar mediante `requestAnimationFrame`. Maneja play/pause, control de velocidad (0.5x–2x), navegación manual e intercambios atómicos del buffer de fotogramas para garantizar la continuidad.

**Métodos principales:**

```text
setFrames(frames) — Intercambia el buffer de fotogramas de forma atómica
play() / pause() — Inicia/detiene la reproducción
nextFrame() / previousFrame() — Navegación manual
setSpeed(speed) — Establece el multiplicador de velocidad (0.5–2.0)
getCurrentFrameIndex() — Obtiene la posición actual
```

**Estado interno:** `currentFrameIndex`, `isPlaying`, `speed`, `frames[]`, `_rafHandle`

**Diferencia clave respecto a v1:** Usa `requestAnimationFrame` (no `setInterval`); el intercambio del buffer de fotogramas mediante `setFrames()` es atómico y nunca detiene la animación.

---

### 5. **controls.js** — Manejadores de controles de la UI

**Archivo:** [`frontend/public/js/shared/controls.js`](../../frontend/public/js/shared/controls.js)

**Responsabilidad:** Gestiona todos los paneles de control de la UI, botones y visualizaciones de estado. Completa/actualiza selectores (checkboxes de radar, desplegable de producto, botones de ventana de tiempo), actualiza las notificaciones de estado y habilita/deshabilita botones según el estado de la aplicación.

**Métodos principales:**

```text
populateRadarCheckboxes(radars) — Construye el panel de selección de radares
sortRadarsForDisplay(radars) — Ordena activos→inactivos, RMA→AR, numérico ascendente
populateProductSelect(products) — Construye el desplegable de productos
setTimeRangeValues(start, end) / getTimeRangeValues() — Sincroniza fecha/hora canónica
initTimeWheels() / refreshTimeWheels() — Inicializa/re-centra los TimeWheels
updateStatus(message, duration) — Muestra un toast de estado temporal
updateFrameCounter(current, total) — Muestra el contador de fotogramas
togglePanel(panelId) — Abre/cierra paneles flotantes
```

**Dependencias:** `shared/time-wheel.js`; en caso contrario, solo manipulación del DOM

**Elementos DOM modificados:** Checkboxes de entrada, desplegables, badges de span, divs de notificación, estados de botones

---

### 5b. **time-wheel.js** — Selector HH:MM estilo iOS

**Archivo:** [`frontend/public/js/shared/time-wheel.js`](../../frontend/public/js/shared/time-wheel.js)

**Responsabilidad:** Un selector de hora compacto con scroll-snap (dos columnas: horas 00–23, minutos 00–59) con una banda de selección centrada, utilizado por el control de rango de tiempo personalizado. Reemplaza el selector de tiempo nativo `datetime-local`.

**Clase `TimeWheel`:**
- `new TimeWheel(container, { onChange })` — Construye las dos columnas; `onChange(hour, minute)` se dispara después de que el usuario selecciona un valor (debounce de fin de scroll ~120 ms, o tap para seleccionar)
- `set(hour, minute)` — Establece el wheel sin disparar `onChange`
- `refresh()` — Reaplica las posiciones de scroll + resaltado (debe llamarse cuando el wheel se vuelve visible, ya que `scrollTop` no puede establecerse mientras está oculto)

**Integración:** `controls.js` posee dos wheels (`startWheel`, `endWheel`). Se combinan con entradas nativas `type="date"` para manejar las entradas **canónicas ocultas** `#start-date`/`#end-date` de tipo `datetime-local` (la única fuente de verdad leída por el resto de la aplicación). Los estilos se encuentran en `styles.css` (`.time-wheel`, `.tw-col`, `.tw-item`, `.tw-selection`).

---

### 6. **legend.js** — Renderizador de leyenda

**Archivo:** [`frontend/public/js/shared/legend.js`](../../frontend/public/js/shared/legend.js)

**Responsabilidad:** Obtiene datos de colormap de la API y renderiza una leyenda interactiva que muestra la correspondencia color-valor. Muestra cuadros de color con etiquetas de valor y descripciones; soporta toggle de mostrar/ocultar.

**Métodos principales:**

```text
render(productKey) — Obtiene colormap vía api.js y construye la leyenda en el DOM
show() / hide() — Alterna la visibilidad de la leyenda
clear() — Elimina todas las entradas de la leyenda
render(colormap, { filterVmin, filterVmax }) — Renderiza con rango de filtro separado
```

**Dependencias:** `api.js` (llama a `getColormapInfo`)

**Elementos DOM modificados:** div `#legend-container` con elementos de cuadro de color + etiqueta anidados

**Formato de renderizado:** Por cada entrada de referencia: cuadrado de color (color hex), valor y título opcional

---

### 7. **tops-cores.js** — Capa de Tops y Núcleos

**Archivo:** [`frontend/public/js/shared/tops-cores.js`](../../frontend/public/js/shared/tops-cores.js)

**Responsabilidad:** Gestiona dos paneles Leaflet — uno para los rellenos de polígono blob de núcleos convectivos y otro para los marcadores SVG de núcleos — que muestran núcleos convectivos, topes de tormenta y huellas blob detectados por radarlib. Los datos se pre-cargan al inicio para todos los frames de animación y se muestran de forma sincrónica en cada avance de frame.

**Arquitectura: Pre-carga + Visualización Sincrónica**

Todos los datos se cargan al inicio en lugar de obtenerse por frame:
- `loadForFrames(frames)` — emite una consulta de metadatos que cubre todo el rango temporal, obtiene todos los registros GeoJSON de forma concurrente via `Promise.all`, luego distribuye los resultados en tablas de búsqueda por frame (`_frameData`, `_frameBlobData`).
- `showFrame(frameIndex)` — sincrónico (sin async); limpia y repinta ambos grupos de capas desde los arreglos pre-cargados. Llamado directamente desde el bucle de animación.

**Dos Paneles:**

| Panel | z-index | Contenido |
|---|---|---|
| `topsCoresBlobPane` | 440 | Rellenos de huella `L.polygon` blob (debajo de los marcadores) |
| `topsCoresPane` | 450 | Íconos SVG de núcleos `L.marker` |

**Métodos Clave:**
- `loadForFrames(frames)` — Pre-carga todos los datos para un conjunto completo de frames de animación (fire-and-forget; cancela cualquier llamada anterior en vuelo)
- `showFrame(frameIndex)` — Sincrónico; limpia ambos grupos de capas y repinta desde los datos pre-cargados
- `setVisible(visible)` — Activa/desactiva ambos paneles; gestiona `_layerGroup` y `_blobLayerGroup`
- `setPointSize(radius)` — Actualiza todos los tamaños de íconos SVG de marcadores (valor crudo del slider × 4 = tamaño en px)
- `clear()` — Elimina todas las capas de ambos grupos
- `destroy()` — Elimina ambos grupos del mapa y cancela cualquier carga en vuelo

**Estilo Visual:**
- **Polígonos blob** (`L.polygon`): `color: '#ff6600'`, `weight: 1.5`, `opacity: 0.8`, `fillColor: '#ff9900'`, `fillOpacity: 0.25` — relleno naranja semi-transparente con borde naranja
- **Marcadores de núcleo** (`L.marker`): ícono SVG en `/img/icono_HT.svg`, por defecto 16 px (slider por defecto 4 × factor de escala 4), anclaje centrado
- **Tooltip:** `"Core — {dbz} dBZ<br>Top — {alt} m"` mostrado al pasar el cursor; la altitud del tope se empareja con el Point de tope más cercano por distancia euclidiana cuadrada en coordenadas geográficas

**Tipos de features GeoJSON manejados:**
- `Point` + `type: "core"` → marcador SVG ubicado en `[lat, lon]`; `intensity_dbz` usado en tooltip
- `Point` + `type: "top"` → solo fuente de altitud; emparejado con el núcleo más cercano; no se renderiza marcador separado
- `Polygon` + `type: "blob"` → anillo exterior `coordinates[0]` renderizado como relleno naranja en `topsCoresBlobPane`

**Persistencia de estado:** `webmet25_tops_cores_visible`, `webmet25_tops_cores_size` en `localStorage`.

**Integración:** Restringido a los productos COLMAX y COLMAXo; el toggle aparece en el panel de configuración de campo.

---

### 9b. **radar-app.js** — Orquestador de la página de un solo radar

**Archivo:** [`frontend/public/js/v2/radar-app.js`](../../frontend/public/js/v2/radar-app.js)

**Responsabilidad:** Orquestador de `radar.html` — la vista de detalle de un solo radar. Gestiona un sistema de capas múltiples, configuraciones de renderizado por capa, línea de tiempo de fotogramas compartida, actualización en vivo y exportación de instantáneas basada en canvas. Reutiliza `MapManager`, `AnimationController` y `UIControls` de los módulos compartidos de v2, pero ejecuta un objeto `state` independiente (sin relación con `app.js`).

**Punto de entrada:** `radar.html?code=<RADAR_CODE>[&field=<PRODUCT_KEY>]`
- `code` es obligatorio; si falta → redirige a `index.html`.
- `field` establece la capa inicial; recurre a `DBZHo` → `COLMAXo` → primero disponible.

**Estructura del estado:**
```javascript
const state = {
    radarCode, radar,
    mapManager, animator, ui,
    products: [],       // available CD-mode products for this radar
    frames: [],         // shared timestamp buckets [{timestamp, cogsByRadar}]
    layers: [],         // active layer objects (see layer shape below)
    nextLayerId,
    liveHours, liveRefreshTimer, animationMode,
    pickerContext, pickerShowFiltered,
};
```

**Estructura del objeto capa:**
```javascript
{
    id, productKey, productTitle,
    opacity,            // 0–1; default 1.0 for first layer, DEFAULT_FIELD_OPACITY otherwise
    visible,
    colormap,           // {vmin, vmax, colors, ticks, colormap, available_colormaps, …}
    selectedColormap,   // overridden colormap name (null = product default)
    vmin, vmax,         // filter bounds (null = no filter sent to API)
    smoothingEnabled, smoothingSigma,   // Gaussian smooth params
    coverageRadius,     // metres from COG tag (null = radar.img_radio * 1000)
    zIndex,
    settingsExpanded,   // Ajustes sub-panel collapse state
    cogsByFrame,        // Map<frameIndex, cog> — COG propio de esta capa por slot de frame
}
```

**Funciones principales:**

| Función | Propósito |
|---|---|
| `addLayer(productKey)` | Obtiene colormap → crea capa → carga fotogramas → re-renderiza la lista |
| `removeLayer(layerId)` | Desmonta overlays + entradas de fotograma → refresca la visualización |
| `swapLayerField(layerId, newKey)` | Reemplaza el campo en su lugar; resetea vmin/vmax/colormap |
| `getTileParamsForLayer(layer)` | Retorna `{colormap, vmin, vmax, smooth, smoothSigma}` para la construcción de URLs |
| `reloadLayerWithNewParams(layer)` | Re-obtiene todos los fotogramas de una capa en paralelo; NO llama a `renderLayerList()` |
| `setLayerColormap(layerId, name)` | Obtiene nueva información de colormap → re-renderiza el strip → recarga fotogramas |
| `loadLayerFramesForRange(layer, start, end)` | Construye `layer.cogsByFrame` (asignación ceiling-slot); carga imágenes en `_frameImages` compartido usando el COG propio de cada capa por slot — permite coexistencia correcta de vol01 y vol02 |
| `showAllLayersAtFrame(index)` | Compone todas las capas visibles en un índice de fotograma; se llama en cada tick de animación |
| `refreshLiveWindow()` | Ancla a los datos más recientes, resetea la estructura de fotogramas, recarga todas las capas |
| `renderLayerList()` | Reconstruye el DOM `#layer-list`; se llama después de cambios estructurales |
| `updateCoverageRadius()` | Recalcula el recorte de la máscara SVG + anillos de cobertura a partir de los radios de las capas activas |

**Panel-module-b — Panel de campo/capa:**
- Las capas activas se renderizan como filas arrastrables (el handle ⠿ activa `draggable` en la fila);
  cada fila tiene: toggle de ojo, nombre de campo (click → modal de cambio), eliminar (✕), strip de colormap +
  ticks, deslizador de opacidad, sub-panel **Ajustes** plegable.
- Controles del sub-panel **Ajustes** (por capa):
  - *Colormap* — `<select>` agrupado por Predeterminado / Otros; se aplica automáticamente al cambiar (sin botón Aplicar)
  - *Rango* — vmin/vmax `<input type="number">` pre-cargado con los valores por defecto del producto cuando `layer.vmin == null`; "Aplicar" dispara `reloadLayerWithNewParams`
  - *Suavizado* — checkbox (on/off) + deslizador de sigma (0.3–3.0, paso 0.1); el cambio del deslizador tiene debounce de 400 ms antes de recargar
- Sección plegable "Añadir campo": lista de checkboxes (toggle sin filtrar/filtrado mediante
  `#toggle-field-picker-filtered`); marcar → `addLayer`, desmarcar → `removeLayer`

**Invariante del filtro de rango (importante):**
`vmin`/`vmax` pasados al endpoint de fotogramas son **únicamente límites de enmascaramiento alfa** — los píxeles fuera del rango se vuelven transparentes. La normalización del colormap siempre usa los valores por defecto del producto de `colormap_for_field()`. La UI pre-carga las entradas con `layer.colormap.vmin/vmax` para que hacer click en "Aplicar" sin acotar el rango sea visualmente una no-operación (coincide con el comportamiento de la página principal). `reloadLayerWithNewParams` no re-renderiza el strip del colormap, por lo que los ticks permanecen con los valores por defecto del producto después de cualquier aplicación de filtro.

**Anillos de cobertura:**
`updateCoverageRadius()` recopila los valores únicos de `layer.coverageRadius`; el recorte de la máscara SVG utiliza el mayor. `MapManager.setRadarCoverageRings()` dibuja un anillo SVG por cada radio único; el anillo más interior (el radio más pequeño dentro del área iluminada) recibe un estilo más destacado.

**Instantánea (`captureMapSnapshot`):**
Pipeline de composición en canvas:
1. Tiles de basemap + imágenes de overlay del radar (respeta la opacidad por overlay)
2. Máscara SVG de cobertura (serializada a blob → dibujada mediante `Image`)
3. Overlay del logo OHMC (arriba a la izquierda, desde `#logo-container img`)
4. Panel de encabezado del radar (arriba al centro, `${code} — ${title}`)
5. Strips de colormap por capa con el timestamp actual (abajo a la izquierda; una fila por capa visible)
6. Panel de tiempo de respaldo (abajo a la derecha, solo cuando no hay capas visibles)

**Dependencias:** `shared/api.js`, `v2/map.js`, `v2/animation.js`, `shared/controls.js`,
`v2/radar-utils.js`, `v2/constants.js`

---

### 9. **cog-browser.js** — [Alternativo] Aplicación de navegación de COG

**Archivo:** [`frontend/public/js/shared/cog-browser.js`](../../frontend/public/js/shared/cog-browser.js)

**Responsabilidad:** Implementación alternativa del frontend para la navegación e inspección detallada de archivos COG (`cog-browser.html`). Provee una vista tabular de los metadatos de COG con ordenamiento/filtrado, separada de la vista principal del mapa animado.

**Propósito:** Para que desarrolladores/operadores inspeccionen archivos COG individuales, timestamps, tamaños de archivo, parámetros de renderizado y estado

**Nota:** Es una vista secundaria; la visualización de radar principal usa `app.js`

---

## Páginas HTML

### **radar.html** — Página de detalle de un solo radar

**Archivo:** [`frontend/public/radar.html`](../../frontend/public/radar.html)

**Responsabilidad:** Esqueleto DOM de la vista de detalle de un solo radar. Se carga como
`/radar.html?code=<RADAR_CODE>`. Solo accesible cuando `Radar.detail_view_enabled = true`
(se configura por radar en el panel de administración). Reutiliza el mismo `styles.css` y la versión de Leaflet que `index.html`, pero tiene su propio diseño: un botón de retroceso + barra de encabezado del radar (arriba al centro), barra de iconos (arriba a la derecha), contenedor del mapa, paneles flotantes (selección de campo/capa, ventana de tiempo, configuración) y controles de animación (abajo al centro).

**Elementos DOM principales:**
- `#radar-header` — muestra el código + título del radar; contiene `#btn-back` (→ `index.html`)
- `#panel-module-b` — panel de selección de campo/capa; contiene `#layer-list` (capas activas,
  construido por `renderLayerList()`) y el `#section-add-field` plegable con `#field-picker-list`
- `#field-picker-modal` — modal de cambio de campo (grilla de todos los productos); separado del panel de agregar campo
- `#panel-module-c` — panel de ventana de tiempo (botones preestablecidos + rango personalizado con TimeWheels)
- `#settings-panel` — selector de basemap, deslizador de opacidad de cobertura, atajos de teclado
- `#animation-controls` — play/pause, botones de navegación, deslizador de velocidad, contador de fotogramas, visualización del tiempo, indicador en vivo, botón de actualización
- `#field-loading-badge` — mostrado mientras se carga una capa

**Scripts cargados:** Leaflet 1.9.4 (CDN), `js/v2/radar-app.js` (módulo ES)

---

### **index.html** — Página principal de visualización de radar

**Archivo:** [`frontend/public/index.html`](../../frontend/public/index.html)

**Responsabilidad:** Define el esqueleto DOM de la aplicación principal de visualización de radar. Contiene contenedores para el mapa Leaflet, barra de iconos (botones de módulo), paneles flotantes (selectores de radar/producto/tiempo), controles de animación, leyenda y visualizaciones de estado.

**Elementos DOM principales:**
- `<div id="map">` — Contenedor del mapa Leaflet
- `<div id="icon-bar">` — Barra de botones vertical (radar, producto, tiempo, instantánea, configuración)
- `<div id="panel-module-a/b/c">` — Paneles de control flotantes
- `<div id="animation-controls">` — Play/pause, velocidad, contador de fotogramas
- `<div id="legend-container">` — Visualización de la leyenda
- `<div id="status">` — Área de notificación de estado
- `<script type="module" src="js/app.js">` — Punto de entrada

**Scripts cargados:**
- Leaflet 1.9.4 (CDN)
- Proveedores de basemap CartoDB (CDN)
- Módulos locales mediante importaciones ES6 en `app.js`

---

### **admin.html** — SPA del panel de administración

**Archivo:** [`frontend/public/admin.html`](../../frontend/public/admin.html)

**Responsabilidad:** Esqueleto DOM del panel de administración — barra lateral (logo OHMC + navegación de secciones agrupadas + "← Volver al mapa"), encabezado con botón de retroceso, un modal de formulario genérico y el modal del creador de colormap. Se sirve en `/admin` detrás de la autenticación HTTP Basic Auth de nginx.

**Scripts cargados:** `js/admin.js` (que importa `js/admin-api.js`). Con estilo de `css/admin.css` (tema moderno claro).

---

## Panel de administración

> Una aplicación de administración de página única independiente para CRUD sobre cada tabla de la base de datos, más un creador/editor visual de colormap. Independiente del frontend de visualización v1/v2. **Autenticación:** HTTP Basic Auth temporal de nginx en `/admin` y `/api/v1/admin/*` (ver [`frontend/nginx.conf`](../../frontend/nginx.conf)); **TODO: reemplazar con JWT.**

### A. **admin.js** — Orquestador de administración

**Archivo:** [`frontend/public/js/admin.js`](../../frontend/public/js/admin.js)

**Responsabilidad:** Renderiza y conecta cada sección de administración, el sistema de filtrado/ordenamiento y el creador/editor de colormap.

**Secciones (enrutadas por hash):** `dashboard`, `radars`, `products`, `references`, `cogs`, `tops-cores`, `estrategias`, `volumenes`, `colormaps`, `colormap-options`.

**Navegación y retorno al mapa:**
- Los cambios de sección usan `history.replaceState` para que la navegación en el admin **nunca agregue** entradas al historial del navegador.
- El mapa principal enlaza aquí desde su **panel de configuración** (`#admin-link`), estableciendo una bandera `sessionStorage` por pestaña: `webmet25_admin_from_main`.
- **← Volver al mapa** llama a `history.back()` cuando esa bandera está establecida (el bfcache del navegador restaura el mapa tal como estaba), de lo contrario navega a `/`.

**Filtrado y ordenamiento (estilo Django-admin):**
- `FILTER_CONFIG` declara las facetas por sección. `renderFilterBar` construye una búsqueda global + controles de facetas por columna; `applyRowFilters` muestra/oculta filas puramente en el DOM (sin recarga, sin pérdida de foco); `wireFilterBar` los vincula. Tipos de faceta: `text` (subcadena), `select` (valores distintos), `boolean` (Sí/No). Conteo de resultados en tiempo real.
- Cada encabezado de columna relevante es ordenable (`wireSortHeaders` + `switchSort`), con indicadores ▲/▼ mediante `decorateSortHeaders`.
- COGs/Tops usan filtros del lado del servidor (paginados) más una búsqueda rápida del cliente sobre la página cargada.

**Acciones de fila:** íconos SVG inline — lápiz (`ICON_EDIT`) y papelera (`ICON_TRASH`), teñidos con `currentColor`.

**Creador/editor de colormap (`openColormapCreator`):**
- Vista previa de gradiente horizontal en tiempo real (`<canvas>` + `createLinearGradient`) con **ticks de stop arrastrables** (pointer events) superpuestos; las filas de stop tienen deslizador + número + muestra de color; asignación de producto como chips de toggle.
- **Crear:** `POST /colormap-from-hex`. **Editar:** pre-carga desde los stops hex reconstruidos (`stopsToHexStops`) + productos asignados actualmente, luego elimina y recrea (`DELETE /colormap-stops/{name}` → `POST /colormap-from-hex`) y reconcilia las opciones (no existe endpoint de actualización). El nombre es de solo lectura en modo edición.
- Después de cualquier cambio: `POST /api/v1/colormap/cache/invalidate`.

**Ver stops:** muestra el gradiente renderizado real (desde `/api/v1/colormap/colors/{name}`) más la tabla de stops del canal.

**Opciones de colormap:** agrega y edita los emparejamientos producto↔colormap (editar = crear nuevo + eliminar antiguo).

### B. **admin-api.js** — Cliente REST de administración

**Archivo:** [`frontend/public/js/admin-api.js`](../../frontend/public/js/admin-api.js)

**Responsabilidad:** Cliente liviano para `/api/v1/admin/*` (base `ADMIN_API_BASE`). Expone CRUD por recurso (radars, products, references, cogs, estrategias, volumenes, tops-cores), stops/resúmenes de colormap, `createColormapFromHex`, opciones de colormap y `getDashboardCounts()`. Muestra los errores 401 como mensaje de sesión expirada; desenvuelve los errores `{detail}`.

### C. **admin.css** — Estilos del panel de administración

**Archivo:** [`frontend/public/css/admin.css`](../../frontend/public/css/admin.css)

**Responsabilidad:** Tema moderno claro (diferente del tema oscuro de la aplicación principal): barra lateral con gradiente agrupado, tablas sticky/zebra/hover, tarjetas con sombra suave, barra de filtros, botones de acción con íconos compactos (`.ico`, `:has(.ico)`), y el creador de colormap (vista previa de gradiente, `.creator-stop-tick` arrastrable, chips de producto).

---

## Estilos

### **styles.css** — Estilos de la aplicación principal

**Archivo:** [`frontend/public/css/styles.css`](../../frontend/public/css/styles.css)

**Responsabilidad:** Hoja de estilos de la aplicación principal de visualización — tema oscuro (fondo `#1a1a2e`, texto claro, acento `#4fc3f7`), diseño responsivo, todos los paneles/controles flotantes y los estilos del **TimeWheel** de rango personalizado (`.time-wheel`, `.tw-col`, `.tw-item`, `.tw-selection`).

> El **panel de administración** usa una hoja de estilos separada, [`css/admin.css`](../../frontend/public/css/admin.css) (tema moderno claro) — ver el componente *Panel de administración*.

**Secciones principales:**
- **Esquema de colores:** Fondo oscuro, acentos, estados hover
- **Distribución:** Flexbox/grid para diseño responsivo
- **Componentes:** Botones de ícono, paneles flotantes, controles de animación, leyenda, notificaciones de estado
- **Puntos de quiebre responsivos:** Tamaños móvil, tablet, escritorio
- **Accesibilidad:** Estados de foco, relaciones de contraste, HTML semántico

**Sin frameworks CSS externos** — CSS3 puro

---

## Grafo de dependencias de módulos

```
index.html (multi-radar map)
└── v2/app.js (main orchestrator)
    ├── shared/api.js (REST client)
    ├── v2/map.js (Leaflet wrapper — L.imageOverlay + SVG coverage mask)
    │   └── Leaflet (CDN)
    ├── v2/animation.js (frame player — requestAnimationFrame)
    │   └── v2/map.js
    ├── shared/controls.js (UI handlers)
    │   └── shared/time-wheel.js (custom-range HH:MM picker)
    ├── shared/legend.js (color scale renderer)
    │   └── shared/api.js
    ├── shared/tops-cores.js (polígonos blob + marcadores SVG)
    │   └── shared/api.js
    └── styles.css

radar.html (one-radar detail page)
└── v2/radar-app.js (one-radar orchestrator)
    ├── shared/api.js (REST client — shared)
    ├── v2/map.js (Leaflet wrapper — shared)
    │   └── Leaflet (CDN)
    ├── v2/animation.js (frame player — shared)
    │   └── v2/map.js
    ├── shared/controls.js (UI handlers — shared)
    │   └── shared/time-wheel.js
    ├── v2/radar-utils.js (waitForLeaflet, updateRadarHeader, buildGridFrames, …)
    ├── v2/constants.js (MS_PER_HOUR, DEFAULT_*, COVERAGE_MODES)
    └── styles.css

admin.html (admin SPA, /admin, Basic Auth)
├── js/admin.js (CRUD, filters/sort, colormap creator/editor)
│   └── js/admin-api.js (/api/v1/admin/* client)
└── css/admin.css (modern-light theme)
```

---

## Flujo de datos a través de los componentes (v2 — mapa principal)

```
1. User opens http://localhost
   ↓
2. index.html loads → v2/app.js:init() called
   ├── api.getRadars() → state.radars
   ├── api.getProducts() → state.products
   ├── MapManager.init() → initialize Leaflet map + SVG coverage pane
   ├── controls.populateRadarCheckboxes(state.radars)
   ├── controls.populateProductSelect(state.products)
   ├── legend.render(defaultProduct)
   └── geolocation → auto-select nearest radars (up to 3), load COLMAX 1.5h
   ↓
3. User selects radar(s) and product
   ├── _loadFramesWithContinuity() called (never stops animation)
   │   ├── api.getCogs(radars, product, strategy, volNrs, timeRange)
   │   ├── buildGridFrames() → grupos por límite de 10 min (ceiling)
   │   ├── pre-fetch frame images: GET /frames/{id}/image.png
   │   └── animator.setFrames(stagingFrames)  ← atomic swap
   └── legend.render(selectedProduct)
   ↓
4. Animation loop (requestAnimationFrame)
   ├── For each tick:
   │   ├── animator advances frameIndex
   │   ├── MapManager.showFrame(index)  ← sets L.imageOverlay URL
   │   ├── controls.updateFrameCounter()
   │   └── topsCoresLayer.showFrame(index)  ← sincrónico (datos pre-cargados)
   └── Continues uninterrupted during field/colormap changes
   ↓
5. User changes field, colormap, or range filter
   └── _loadFramesWithContinuity() → background reload → atomic swap
   ↓
6. Coverage mode toggle (C+D ↔ VIG)
   ├── Updates active mode → different volNrs
   └── _loadFramesWithContinuity() with new volNrs
   ↓
7. Live refresh (every 1 min)
   └── refreshLiveWindow() → incremental diff → animator.setFrames()
```

## Flujo de datos a través de los componentes (página de un solo radar)

```
1. User opens /radar.html?code=AR5[&field=DBZHo]
   ↓
2. radar-app.js:init() called
   ├── api.getRadars() + api.getProducts(CD_MODE) → state.radar, state.products
   ├── MapManager.init() → Leaflet map centered on radar, SVG coverage pane
   ├── updateRadarHeader(radar) → fills #radar-header-code / #radar-header-title
   ├── fitMapToRadar(radar, mapManager) → sets map bounds to radar coverage
   └── addLayer(initialProductKey)  ← DBZHo / field param / first available
       ├── api.getColormapInfo(productKey) → layer.colormap
       ├── creates layer object with vmin=null, vmax=null, smoothingEnabled=false
       ├── loadLayerFrames(layer, storedHours)
       │   ├── api.getLatestCogsForRadars() → anchor end time
       │   ├── loadLayerFramesForRange(layer, start, end)
       │   │   ├── api.getCogsForTimeRange() → COG list
       │   │   ├── buildGridFrames() → state.frames (slots de 10 min, ceiling)
       │   │   ├── For each frame: _buildFrameUrl(cogId, productKey, params)
       │   │   │   → GET /frames/{id}/image.png?colormap=…&vmin=…&vmax=…&smooth=…
       │   │   ├── _loadImage(url) → {img, bbox, objectUrl}
       │   │   └── stored in state.mapManager._frameImages[frameIdx].set(key, entry)
       │   └── animator.updateFrames(state.frames, …) → start playback
       └── startLiveRefresh(storedHours)
   ↓
3. Animation loop (requestAnimationFrame)
   ├── animator._showCurrentFrame() overridden → showAllLayersAtFrame(index)
   │   ├── hide all overlays
   │   └── for each visible layer: overlay.setUrl(entry.img.src) + setOpacity(opacity)
   └── updateCoverageRadius() called on layer add/remove
       ├── collect unique coverageRadius values from state.layers
       ├── addRadarCoverage(…, maxRadius)  ← mask cutout = union
       └── setRadarCoverageRings(…, uniqueRings)  ← one ring per unique radius
   ↓
4. User adds a field (checkbox or modal)
   └── addLayer(productKey) → new layer merged into existing state.frames
   ↓
5. User changes per-layer setting (colormap / range / smoothing)
   ├── Colormap change: setLayerColormap() → fetch new info → re-render strip → reloadLayerWithNewParams()
   ├── Range filter (Apply): layer.vmin/vmax = parsed inputs → reloadLayerWithNewParams()
   │   ↑ inputs pre-populated with colormap.vmin/vmax (product defaults) when vmin == null
   │   ↑ reloadLayerWithNewParams() does NOT call renderLayerList() — strip ticks unchanged
   └── Smoothing: toggle/sigma → reloadLayerWithNewParams() (sigma debounced 400 ms)
   ↓
6. Live refresh (every LIVE_REFRESH_INTERVAL_MS)
   └── refreshLiveWindow()
       ├── getLatestCogsForRadars(first layer) → new anchor end time
       ├── reset state.frames + _clearAllOverlays()
       └── loadLayerFramesForRange(each layer, newStart, newEnd)
```

---

## Ciclo de vida del estado

Al cargar la página, `init()` inicializa el estado, obtiene los datos y comienza la animación si los radares se seleccionan automáticamente mediante geolocalización. Todos los cambios posteriores (campo, colormap, ventana de tiempo, modo de cobertura) pasan por `_loadFramesWithContinuity()`, que garantiza que la animación nunca se detenga.

---

## Compatibilidad con navegadores

- **Chrome/Edge:** 88+
- **Firefox:** 78+
- **Safari:** 14+
- **Móvil:** Cualquiera con soporte de módulos ES6 (iOS Safari 15+, Android Chrome 80+)

**Requisitos:** Módulos ES6, Fetch API, Leaflet 1.9.4 (CDN), Canvas API.

---

## Principios de diseño fundamentales

1. **Sin herramienta de compilación:** Módulos ES6 puros servidos directamente; sin webpack/vite
2. **Sin framework:** JavaScript puro; manipulación directa del DOM
3. **Módulos de responsabilidad única:** Cada archivo `.js` tiene un propósito claro
4. **Estado global:** El objeto `state` en `v2/app.js` es la fuente de verdad
5. **Continuidad de animación:** Todos los cambios de datos pasan por `_loadFramesWithContinuity()` — la animación nunca se detiene durante la carga
6. **Async/Await:** Patrones asíncronos modernos en todo el código
7. **Diseño responsivo:** CSS mobile-first, tema oscuro

---

**Versión del Documento:** 2.4.0  
**Última Actualización:** 29 de julio de 2026
