# E2E_TESTING.md — Pruebas de Extremo a Extremo (Navegador)

> Versión en español de [E2E_TESTING.md](E2E_TESTING.md).

> **Propósito:** Cómo ejecutar las pruebas de extremo a extremo Playwright de WebMet25, qué cubren y cómo configurar un entorno equivalente **fuera** del stack Docker del proyecto (p. ej. en una máquina sin contenedores o en otro CI).

---

## 1. Qué son estas pruebas

Las pruebas e2e conducen un **Chromium headless real** (vía Playwright) contra el
**frontend v2** + API en ejecución, ejercitando comportamientos que una prueba unitaria no puede:
renderizado, filtrado/ordenamiento del DOM, el canvas del creador de colormaps con arrastre,
y el selector de tiempo con rueda estilo iOS.

**Ubicación:** [`tests/e2e/`](../tests/e2e/)

| Archivo | Funcionalidad bajo prueba |
|---------|--------------------------|
| `test_admin_panel.py` | Panel de administración: carga, logo OHMC, volver al mapa, filtros por columna + búsqueda global, ocultamiento de filas por filtro de texto, columnas ordenables + indicador ▲/▼, acciones de fila con íconos, creador de colormaps (canvas de gradiente, ticks arrastrables, etiqueta "Cerrar") |
| `test_radar_ordering.py` | Mapa principal: carga, regla de ordenamiento de la lista de radares (RMA antes que AR, `RMA00` al final, activos antes que inactivos), presencia del enlace al panel de administración |
| `test_time_wheel.py` | Rango de tiempo personalizado: ambas ruedas se renderizan (24h + 60m = 84 ítems), dos columnas + banda de selección, tap para seleccionar actualiza el campo canónico |
| `conftest.py` | Fixtures compartidos: helper de login + sesión de admin compartida, captura de errores JS, captura de pantalla en caso de falla |

> ⚠️ Estas pruebas requieren el **frontend v2** — la rueda de tiempo solo está integrada por `js/v2/app.js`. Apuntarlas a un frontend v1 hará fallar `test_time_wheel.py`.

---

## 2. Entorno requerido (cualquier framework)

Las pruebas son Python + Playwright independientes del entorno. Para ejecutarlas en cualquier lugar se necesita:

| Requisito | Notas |
|-----------|-------|
| **Python 3.11** | coincide con el proyecto |
| **Paquetes pip** | `pytest`, `pytest-asyncio`, `pytest-playwright` (ver [`tests/requirements.txt`](../tests/requirements.txt)) |
| **Playwright Chromium** | `playwright install chromium` + librerías del sistema `playwright install-deps chromium` |
| **Una API en ejecución** | DB inicializada con datos (radares, productos, los 8 colormaps del sistema). Accesible en `API_BASE_URL`. |
| **Un frontend v2 en ejecución** | nginx sirviendo el build de v2. Accesible en `FRONTEND_URL`. |
| **Una cuenta de admin** | creada por `db-init` a partir de `BOOTSTRAP_ADMIN_USERNAME` / `BOOTSTRAP_ADMIN_PASSWORD` (ver abajo). |
| **Accesibilidad de red** | el host de pruebas debe alcanzar `FRONTEND_URL` (el frontend a su vez hace proxy de `/api/v1/*` hacia la API). |

### Variables de entorno

| Variable | Valor por defecto (devcontainer) | Significado |
|----------|----------------------------------|-------------|
| `FRONTEND_URL` | `http://frontend-v2:80` | URL base del frontend **v2** bajo prueba |
| `API_BASE_URL` | `http://api:8000` | Base de la API (usada por los tests de contrato de la API, no estrictamente por e2e) |
| `BOOTSTRAP_ADMIN_USERNAME` | `admin` | Usuario de la cuenta de admin con la que se loguean los tests |
| `BOOTSTRAP_ADMIN_PASSWORD` | *(ninguno)* | Su contraseña — obligatoria, sin ella los tests no pueden loguearse |

Todas las páginas requieren login. Las pruebas inician sesión por el formulario de `/login` con la cuenta que
`db-init` crea a partir de las mismas variables `BOOTSTRAP_ADMIN_*` de tu `.env`. Los tests del mapa, del detalle de
radar y del panel arrancan ya logueados (`browser_context_args` con el `admin_storage_state` compartido). Un test crea
el viewer `e2e-viewer` por la API de admin (o lo reactiva) y lo desactiva al terminar.

nginx limita `/api/v1/auth/login` a 10 pedidos por minuto por IP, así que las pruebas del panel de admin **comparten un
solo login**: su estado de navegador se reutiliza en todos los tests y se renueva cada 10 minutos (la cookie de acceso
dura 30). No conviene repetir la suite más de unas pocas veces por minuto. Mantener `ACCESS_TOKEN_TTL_MINUTES` en 15 o
más mientras se corren las suites: el login compartido se reutiliza hasta 10 minutos y `tests/api` se loguea una vez por
corrida.

---

## 3. Ejecución dentro del proyecto (Docker — recomendado)

El stack de desarrollo ya incluye un servicio `tests` (Playwright + Chromium preinstalados en
[`tests/Dockerfile`](../tests/Dockerfile)).

```bash
# Desde la raíz del repositorio. Compose con ambos archivos (base + override del devcontainer).
DC="docker compose -f docker-compose.yml -f docker-compose.devcontainer.yml"

# 1. Levantar la API, un frontend v2, la DB de pruebas y el contenedor de tests.
$DC up -d --build radar_db redis db-init api frontend-v2 radar_db_test db-init-test tests

# 2. Ejecutar el conjunto de pruebas e2e dentro del contenedor de tests.
docker exec radar_tests pytest tests/e2e/ -v

# Ejecutar un único archivo / test:
docker exec radar_tests pytest tests/e2e/test_admin_panel.py -v
docker exec radar_tests pytest tests/e2e/test_time_wheel.py::test_time_wheels_render -v

# Detener cuando termine:
$DC down            # agregar -v para también eliminar los volúmenes
```

**Credenciales de admin:** definirlas una vez en un `.env` en la raíz del repositorio (Compose lo lee):
```dotenv
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=your-strong-password   # 12+ caracteres
```
`db-init` crea la cuenta con ellas y el servicio `tests` lee los mismos valores, así que se mantienen consistentes.

**Capturas de pantalla en caso de falla** se escriben en `tests/e2e/screenshots/` (ignorado por git). Para copiarlas fuera del contenedor:
```bash
docker cp radar_tests:/app/tests/e2e/screenshots ./e2e-screenshots
```

> El conjunto completo también puede ejecutarse con `docker exec radar_tests pytest` (api + indexer + e2e). Ver [`.github/copilot-instructions.md`](../.github/copilot-instructions.md) → *Testing Strategy*.

---

## 4. Ejecución fuera de Docker (máquina local / otro CI)

Usar esto cuando no se dispone del stack Docker — p. ej. una laptop o un runner de CI genérico.
Igual se necesita una API + frontend v2 accesibles desde el host de pruebas (levantarlos de la forma
que se prefiera; el fragmento a continuación usa los propios contenedores del proyecto solo para esos dos).

```bash
# 0. Tener una API + frontend v2 corriendo en algún lugar y anotar sus URLs.
#    (Forma mínima con el proyecto: `docker compose up -d radar_db redis db-init api`
#     y servir el frontend v2 — ver frontend/Dockerfile, FE_VERSION=v2.)

# 1. Entorno Python
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r tests/requirements.txt

# 2. Navegador Playwright + librerías del SO
playwright install chromium
playwright install-deps chromium      # requiere sudo en Debian/Ubuntu

# 3. Apuntar los tests a los servicios en ejecución + credenciales de admin
export FRONTEND_URL="http://localhost:8090"   # tu frontend v2
export BOOTSTRAP_ADMIN_USERNAME="admin"
export BOOTSTRAP_ADMIN_PASSWORD="your-strong-password"

# 4. Ejecutar (PYTHONPATH=tests para que los tests puedan `from conftest import ...`)
PYTHONPATH=tests pytest tests/e2e/ -v
```

### Esquema genérico para CI (estilo GitHub Actions)
```yaml
- uses: actions/setup-python@v5
  with: { python-version: "3.11" }
- run: pip install -r tests/requirements.txt
- run: playwright install --with-deps chromium
- run: PYTHONPATH=tests pytest tests/e2e/ -v
  env:
    FRONTEND_URL: http://localhost:8090
    BOOTSTRAP_ADMIN_USERNAME: admin
    BOOTSTRAP_ADMIN_PASSWORD: ${{ secrets.E2E_ADMIN_PASSWORD }}
```
(Iniciar la API + frontend v2 en un paso anterior / contenedor de servicio, p. ej. vía
`docker compose up -d`.)

### Ciclo de desarrollo local rápido (con interfaz gráfica / debug)
Ejecutando directamente (no en el contenedor) se puede ver el navegador y recorrerlo paso a paso:
```bash
PYTHONPATH=tests pytest tests/e2e/ --headed --slowmo 300        # verlo ejecutar
PYTHONPATH=tests PWDEBUG=1 pytest tests/e2e/test_admin_panel.py # Playwright Inspector
```

---

## 5. Resolución de problemas

| Síntoma | Causa / solución |
|---------|-----------------|
| `error while loading shared libraries: libnspr4.so` | Librerías del SO para Chromium ausentes → `playwright install-deps chromium` (sudo). |
| Las pruebas de admin terminan en `/login`, o reciben 401 / 429 | `BOOTSTRAP_ADMIN_*` no coinciden con una cuenta de admin existente, o `/api/v1/auth/login` fue limitado (10/min por IP): esperar un minuto y repetir. |
| `test_time_wheels_render` falla con `items=0` | `FRONTEND_URL` apunta a un frontend **v1**. Apuntarlo al frontend v2. |
| `net::ERR_CONNECTION_REFUSED` | `FRONTEND_URL` no es accesible desde el host de pruebas (host/puerto incorrecto, o frontend no iniciado). |
| Orden de radares / lista de radares vacía | API sin datos iniciales. Ejecutar `python -m radar_db.manage seed` (el contenedor `db-init` hace esto automáticamente). |
| Las pruebas se cuelgan en `networkidle` | El frontend no puede alcanzar la API (el proxy de nginx `/api/v1` apunta a la API caída). Verificar que la API esté en funcionamiento. |

---

**Versión del Documento:** 1.1.0  
**Última Actualización:** 8 de julio de 2026
