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
| `conftest.py` | Fixtures compartidos: contexto de autenticación básica HTTP, captura de errores JS, captura de pantalla en caso de falla |

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
| **Un frontend v2 en ejecución** | nginx sirviendo el build de v2 con el htpasswd de autenticación básica para el admin. Accesible en `FRONTEND_URL`. |
| **Accesibilidad de red** | el host de pruebas debe alcanzar `FRONTEND_URL` (el frontend a su vez hace proxy de `/api/v1/*` hacia la API). |

### Variables de entorno

| Variable | Valor por defecto (devcontainer) | Significado |
|----------|----------------------------------|-------------|
| `FRONTEND_URL` | `http://frontend-v2:80` | URL base del frontend **v2** bajo prueba |
| `API_BASE_URL` | `http://api:8000` | Base de la API (usada por los tests de contrato de la API, no estrictamente por e2e) |
| `ADMIN_USERNAME` | `admin` | Usuario de autenticación básica HTTP para `/admin` — **debe coincidir** con el htpasswd del frontend |
| `ADMIN_PASSWORD` | `change-me` | Contraseña de autenticación básica HTTP para `/admin` |

El panel de administración está protegido por autenticación básica de nginx; el contenedor del frontend genera su
`admin.htpasswd` a partir de `ADMIN_USERNAME`/`ADMIN_PASSWORD` al iniciar
([`frontend/docker-entrypoint.sh`](../frontend/docker-entrypoint.sh)). Las pruebas se autentican
con los mismos valores vía `http_credentials` de Playwright, por lo que **deben mantenerse sincronizados**.

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

**Credenciales de admin personalizadas:** definirlas en un `.env` en la raíz del repositorio (Compose lo lee):
```dotenv
ADMIN_USERNAME=observatorio
ADMIN_PASSWORD=your-strong-password
```
Tanto el servicio `frontend-v2` como el `tests` las tomarán, manteniendo la autenticación consistente.

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
export ADMIN_USERNAME="admin"
export ADMIN_PASSWORD="change-me"

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
    ADMIN_USERNAME: admin
    ADMIN_PASSWORD: change-me
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
| Las pruebas de admin reciben un 401 / página en blanco | `ADMIN_USERNAME`/`ADMIN_PASSWORD` no coinciden con el htpasswd del frontend. Sincronizarlos (y reconstruir/reiniciar el frontend si se cambió su entorno). |
| `test_time_wheels_render` falla con `items=0` | `FRONTEND_URL` apunta a un frontend **v1**. Apuntarlo al frontend v2. |
| `net::ERR_CONNECTION_REFUSED` | `FRONTEND_URL` no es accesible desde el host de pruebas (host/puerto incorrecto, o frontend no iniciado). |
| Orden de radares / lista de radares vacía | API sin datos iniciales. Ejecutar `python -m radar_db.manage seed` (el contenedor `db-init` hace esto automáticamente). |
| Las pruebas se cuelgan en `networkidle` | El frontend no puede alcanzar la API (el proxy de nginx `/api/v1` apunta a la API caída). Verificar que la API esté en funcionamiento. |

---

**Versión del Documento:** 1.1.0  
**Última Actualización:** 8 de julio de 2026
