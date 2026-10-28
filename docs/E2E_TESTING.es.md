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
| `test_registration_flow.py` | Registro público: registrarse (con el nombre y apellido opcional, que después muestra el panel de cuenta), verificar el mail desde su link y entrar con el mail; una cuenta sin verificar no puede entrar y puede pedir un mail nuevo; recupero de contraseña de punta a punta; el formulario controla las contraseñas; un mail ya registrado muestra la misma pantalla; un link de verificación basura. Los mails se leen de Mailpit (ver abajo) |
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
| **Una cuenta de admin** | creada por `db-init` a partir de `ADMIN_USERNAME` / `ADMIN_PASSWORD` (ver abajo). |
| **Accesibilidad de red** | el host de pruebas debe alcanzar `FRONTEND_URL` (el frontend a su vez hace proxy de `/api/v1/*` hacia la API). |

### Variables de entorno

| Variable | Valor por defecto (devcontainer) | Significado |
|----------|----------------------------------|-------------|
| `FRONTEND_URL` | `http://frontend-e2e:80` | URL base del frontend **v2** bajo prueba (valor por defecto del código: `http://frontend-v2:80`) |
| `API_BASE_URL` | `http://api-e2e:8000` | Base de la API (usada por los tests de contrato de la API, no estrictamente por e2e; valor por defecto del código: `http://api:8000`) |
| `ADMIN_USERNAME` | `admin` | Usuario de la cuenta de admin con la que se loguean los tests |
| `ADMIN_PASSWORD` | *(ninguno)* | Su contraseña — obligatoria, sin ella los tests no pueden loguearse |
| `MAILPIT_URL` | `http://mailpit:8025` | Buzón local del que los tests de registro leen los mails de verificación y de recupero |

**En qué base escribe cada suite.** `tests/api` y `tests/e2e` son de caja negra: pasan por una API y un frontend que
están corriendo, y escriben (el viewer de e2e, las sesiones del admin). En el stack de desarrollo corren contra una
copia aislada, nunca contra tu base principal:

| Suites | Contra qué | Base |
|---|---|---|
| `tests/auth`, `tests/indexer` | en proceso | `radar_test_db` (vacía; cada test se revierte) |
| `tests/api`, `tests/e2e` | `api-e2e`, `frontend-e2e` | `radar_e2e_db`, en su propio contenedor `radar_db_e2e` (la inicializa `db-init-e2e`; los COGs los carga `indexer-e2e`) |
| tu uso | `api`, `frontend-v2` | `radar_prod_db` (ningún test la toca) |

`api-e2e` responde al nombre `api` dentro de la red privada `e2e`, así `frontend-e2e` usa la imagen normal del
frontend con su `nginx.conf` normal. Los servicios de test no publican puertos.

> **Nunca apuntar `API_BASE_URL` ni `FRONTEND_URL` a stage ni al operativo:** las suites crean el usuario
> `e2e-viewer` y sesiones del admin en la base que esté detrás.

Todas las páginas requieren login. Las pruebas inician sesión por el formulario de `/login` con la cuenta que
`db-init` crea a partir de las mismas variables `ADMIN_USERNAME` / `ADMIN_PASSWORD` de tu `.env`. Los tests del mapa, del detalle de
radar y del panel arrancan ya logueados (`browser_context_args` con el `admin_storage_state` compartido). Un test crea
el viewer `e2e-viewer` por la API de admin (o lo reactiva) y lo desactiva al terminar.

nginx limita `/api/v1/auth/login` a 10 pedidos por minuto por IP, así que las pruebas del panel de admin **comparten un
solo login**: su estado de navegador se reutiliza en todos los tests y se renueva cada 10 minutos (la cookie de acceso
dura 30). No conviene repetir la suite más de unas pocas veces por minuto. Mantener `ACCESS_TOKEN_TTL_MINUTES` en 15 o
más mientras se corren las suites: el login compartido se reutiliza hasta 10 minutos y `tests/api` se loguea una vez por
corrida.

**Tests de registro y el buzón local.** `api-e2e` tiene el registro encendido y manda sus mails a **Mailpit** (contenedor `mailpit` del stack de desarrollo, el mismo que usa la API principal; pantalla en `http://localhost:8025`). `test_registration_flow.py` vacía el buzón, lee el mail por la API HTTP de Mailpit (`MAILPIT_URL`) y abre su link contra `FRONTEND_URL`. Para tener en cuenta:

- nginx limita los endpoints de registro (`register`, `verify-email`, `resend-verification`, `forgot-password`, `reset-password`) a 10 pedidos por minuto por IP, con ráfaga de 5, en un contador propio. El archivo hace 13 pedidos de esos, así que sus tests se espacian solos (12 s entre test y test). Si igual aparece un `429`, esperar un minuto y repetir el test que falló.
- `api-e2e` tiene `TERMS_REQUIRED=true`: los tests tildan la casilla de términos. El caso por defecto (sin términos) lo cubren `tests/auth` y los tests de JS.
- `api-e2e` usa `MAIL_MIN_INTERVAL_SECONDS=0`: los tests piden un segundo mail a la misma cuenta apenas después del primero, y con una espera la API responde 202 pero no envía nada. El intervalo en sí lo cubre `tests/auth`.
- Toda cuenta que crean los tests (`e2e-reg-*`) se desactiva al terminar, por la API de admin.
- Los mails usan el dominio `ejemplo.com.ar`: las direcciones `.test` o `.local` las rechaza la validación de mails.

---

## 3. Ejecución dentro del proyecto (Docker — recomendado)

El stack de desarrollo ya incluye un servicio `tests` (Playwright + Chromium preinstalados en
[`tests/Dockerfile`](../tests/Dockerfile)).

```bash
# Desde la raíz del repositorio. Compose con ambos archivos (base + override del devcontainer).
DC="docker compose -f docker-compose.yml -f docker-compose.devcontainer.yml"

# 1. Levantar el stack de desarrollo, el stack de test aislado y el contenedor de tests (igual que `make dev-up`).
$DC up -d --build radar_db redis db-init api frontend-v2 radar_db_test db-init-test radar_db_e2e db-init-e2e api-e2e frontend-e2e indexer-e2e tests

# 2. Ejecutar el conjunto de pruebas e2e dentro del contenedor de tests.
docker exec radar_tests pytest tests/e2e/ -v

# Ejecutar un único archivo / test:
docker exec radar_tests pytest tests/e2e/test_admin_panel.py -v
docker exec radar_tests pytest tests/e2e/test_time_wheel.py::test_time_wheels_render -v

# Al terminar, detener (conserva los contenedores y las bases de test para la próxima corrida):
$DC stop
```

**Credenciales de admin:** definirlas una vez en un `.env` en la raíz del repositorio (Compose lo lee):
```dotenv
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-strong-password   # 12+ caracteres
```
`db-init` (stack principal) y `db-init-e2e` (stack de test) crean la cuenta con ellas y el servicio `tests` lee los
mismos valores, así que se mantienen consistentes.

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
export ADMIN_PASSWORD="your-strong-password"

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
    ADMIN_PASSWORD: ${{ secrets.E2E_ADMIN_PASSWORD }}
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
| Las pruebas de admin terminan en `/login`, o reciben 401 / 429 | `ADMIN_USERNAME` / `ADMIN_PASSWORD` no coinciden con una cuenta de admin existente, o `/api/v1/auth/login` fue limitado (10/min por IP): esperar un minuto y repetir. |
| `test_time_wheels_render` falla con `items=0` | `FRONTEND_URL` apunta a un frontend **v1**. Apuntarlo al frontend v2. |
| `net::ERR_CONNECTION_REFUSED` | `FRONTEND_URL` no es accesible desde el host de pruebas (host/puerto incorrecto, o frontend no iniciado). |
| Orden de radares / lista de radares vacía | API sin datos iniciales. Ejecutar `python -m radar_db.manage seed` (el contenedor `db-init` hace esto automáticamente). |
| Las pruebas se cuelgan en `networkidle` | El frontend no puede alcanzar la API (el proxy de nginx `/api/v1` apunta a la API caída). Verificar que la API esté en funcionamiento. |
| Test de registro: `No llegó un mail a …` | Mailpit no está corriendo o `MAILPIT_URL` está mal, o la API no envió (un tope de mails, o el registro está apagado: `GET /api/v1/auth/options` en `api-e2e` debe mostrar `registration: true`). Mirar `http://localhost:8025`. |
| Test de registro: un elemento no aparece después de un pedido | nginx respondió `429` (los endpoints de registro permiten 10 pedidos por minuto por IP). Esperar un minuto y repetir ese test. |

---

**Versión del Documento:** 1.2.0  
**Última Actualización:** 27 de octubre de 2026
