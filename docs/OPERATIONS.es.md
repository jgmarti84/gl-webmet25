# OPERATIONS.md — Referencia Operativa de WebMet25

> Versión en español de [OPERATIONS.md](OPERATIONS.md).

> Cubre la gestión de disco, la eliminación de productos y otras tareas operativas que no pertenecen a la documentación de flujo de datos ni de componentes.

---

## 1. ProductDeleter — Limpieza Masiva de Disco y Base de Datos

**Archivo:** [`indexer/indexer/deleter.py`](../indexer/indexer/deleter.py)  
**Script CLI:** [`scripts/delete_products.sh`](../scripts/delete_products.sh)

`ProductDeleter` elimina archivos COG del disco **y** sus registros `RadarCOG` correspondientes de la base de datos en una única transacción. Usalo para la gestión rutinaria de retención o para recuperación de espacio en disco de emergencia.

### 1.1 Qué hace

1. Escanea `ROOT_RADAR_PRODUCTS_PATH` en busca de archivos `.tif` que coincidan con los criterios dados (fecha, códigos de radar, claves de producto)
2. Elimina los archivos coincidentes del disco; elimina los directorios padres vacíos
3. Elimina los registros `RadarCOG` coincidentes de la base de datos en una transacción
4. Opcionalmente elimina archivos de log `genpro25.log.YYYY-MM-DD` de `LOGS_PATH`

### 1.2 Ejecutar el Deleter

```bash
# Desde dentro del contenedor indexer:
docker exec radar_indexer python -m indexer.deleter \
    --date 2026-04-01 \
    --radar-codes RMA1,AR5 \
    --product-keys DBZHo,COLMAXo

# Simulación (muestra qué se eliminaría sin eliminar nada):
docker exec radar_indexer python -m indexer.deleter \
    --date 2026-04-01 \
    --dry-run

# Eliminar todos los productos de una fecha específica en todos los radares:
docker exec radar_indexer python -m indexer.deleter --date 2026-04-01
```

### 1.3 Consideraciones de Seguridad

- Siempre ejecutá `--dry-run` primero para verificar el alcance antes de una eliminación destructiva
- La eliminación en la BD es transaccional — si la transacción falla, las eliminaciones del sistema de archivos ya realizadas **no** se revierten. Preferentemente ejecutá durante períodos de baja actividad
- `is_active` en Radar se recalcula en el próximo escaneo de COGWatcher luego de la eliminación

---

## 2. Gestión de Disco de Docker

Comandos de referencia para la limpieza de disco de Docker/containerd. Ver también [`scripts/MANAGE_COMMANDS.md`](../scripts/MANAGE_COMMANDS.md).

### 2.1 Verificar Uso de Disco

```bash
# Resumen de capas y volúmenes de Docker
docker system df

# Desglose detallado
docker system df -v
```

### 2.2 Eliminar Recursos No Utilizados

```bash
# Eliminar contenedores detenidos, imágenes colgantes y redes no usadas (seguro)
docker system prune

# También elimina volúmenes no usados y todas las imágenes sin tag (¡destructivo!)
docker system prune -a --volumes
```

### 2.3 Eliminación Selectiva

```bash
# Eliminar solo imágenes no usadas (conserva las usadas por contenedores en ejecución)
docker image prune -a

# Eliminar solo volúmenes no asociados a un contenedor en ejecución
docker volume prune

# Eliminar un volumen específico (¡destructivo!)
docker volume rm webmet25_radar_db_data
```

### 2.4 Limpieza de Snapshots de containerd (WSL2 / Rancher Desktop)

Si se usa containerd como runtime de Docker (Rancher Desktop en WSL2):

```bash
# Listar namespaces de containerd
sudo ctr namespaces list

# Compactar snapshots no usados en el namespace moby
sudo ctr -n moby snapshots rm $(sudo ctr -n moby snapshots list -q)
```

### 2.5 Vaciar Logs del Journal (WSL2)

```bash
# Mostrar uso de disco del journal
journalctl --disk-usage

# Vaciar logs con más de 7 días de antigüedad
sudo journalctl --vacuum-time=7d

# Vaciar hasta un límite de tamaño
sudo journalctl --vacuum-size=100M
```

---

## 3. Mantenimiento de Base de Datos

### 3.1 Limpieza Manual de Registros COG

```bash
# Abrir una shell interactiva de la BD
docker compose exec db-init python -m radar_db.manage shell

# Eliminar registros MISSING con más de 30 días de antigüedad
from datetime import datetime, timedelta
cutoff = datetime.utcnow() - timedelta(days=30)
deleted = session.query(RadarCOG).filter(
    RadarCOG.status == COGStatus.MISSING,
    RadarCOG.updated_at < cutoff
).delete()
session.commit()
print(f"Deleted {deleted} records")
```

### 3.2 Verificar Estado de la Base de Datos

```bash
# Conteo de filas, radares activos, COGs recientes
docker compose exec db-init python -m radar_db.manage info

# Verificar estado de migraciones
docker compose exec db-init python -m radar_db.manage migrate current
```

### 3.3 Reseteo Completo de Desarrollo

```bash
# Eliminar todas las tablas + recrear + resembrar (solo desarrollo — destruye todos los datos indexados)
docker compose exec db-init python -m radar_db.manage reset --force --seed
```

---

## 4. Verificaciones de Salud del Indexer

```bash
# Ver logs del indexer en tiempo real
docker compose logs -f indexer

# Verificar si el indexer está procesando archivos (buscar líneas de log "Indexed COG")
docker compose logs --tail=50 indexer

# Verificar que el path de vigilancia está montado y tiene archivos
docker exec radar_indexer ls -la /product_output/

# Ejecutar un escaneo único manualmente (one-shot, útil para depuración)
docker exec radar_indexer python -m indexer.main --single --debug

# Verificar conexión a la BD desde el indexer
docker exec radar_indexer python -m indexer.manage check
```

---

## 5. Salud de la API y Caché

```bash
# Verificación de salud
curl http://localhost/api/v1/health

# Ver estadísticas de caché de frames/tiles (L1 LRU + L2 Redis)
curl http://localhost/api/v1/tiles/cache/stats

# Vaciar la caché en proceso de colormaps. Requiere una sesión de admin (el panel de administración y
# scripts/import_colormap.py ya lo hacen por vos); con curl, hay que loguearse primero:
curl -c cj.txt -X POST http://localhost/api/v1/auth/login -H "Content-Type: application/json" -d '{"username":"<admin>","password":"<password>"}'
curl -b cj.txt -X POST http://localhost/api/v1/colormap/cache/invalidate
```

## 6. Gestión de Usuarios

Ejecutar desde la raíz del repo (`gl-webmet25`). Usan la imagen de `db-init`, así que no requieren preparación extra.

```bash
# Crear un admin (pide la contraseña dos veces, sin mostrarla)
make create-admin U=maria

# Poner una contraseña nueva a cualquier usuario y cerrar todas sus sesiones
make reset-password U=maria
```

- El **primer admin** lo crea automáticamente `db-init` a partir de `ADMIN_USERNAME` / `ADMIN_PASSWORD` cuando no hay usuarios. Tras el primer arranque, ejecutar `make reset-password U=<ese usuario>` y borrar ambas variables del `.env`.
- Un admin **no puede resetear su propia contraseña desde el panel**; usar `make reset-password` en el servidor.
- Nadie puede usar la página sin cuenta. El admin crea cuentas desde el panel; las personas también pueden crear la suya cuando el registro público está encendido (ver [§7](#7-registro-público-y-mail)). Un mail cargado por un admin cuenta como verificado.
- Los demás usuarios se gestionan desde el panel de administración (**Usuarios**): crear, cambiar rol, activar/desactivar, resetear contraseña, cerrar sesiones. Desactivar es reversible; **borrar** (abajo) es definitivo.
- **Borrar usuarios:** el admin general borra a otro usuario desde **Usuarios, editar (lápiz), Eliminar usuario** (un botón rojo al pie del formulario), y cada persona puede borrar su propia cuenta desde **Mi perfil, Eliminar mi cuenta**. Los dos piden una confirmación manual y no se pueden deshacer. Solo el admin general borra a OTRAS personas. Un admin de institución no se puede borrar (ni borrarse a sí mismo) si la institución quedaría con usuarios activos y sin admin activo: primero hay que nombrar a otro (409); si es el único usuario activo de la institución, o está inactivo, sí se puede borrar. Un admin general no puede borrar su propia cuenta (lo hace otro admin general). Borrar es real: se borran la cuenta, sus sesiones, sus links de mail y sus vistas de radar propias; "quién dio un permiso", "quién invitó" y "quién editó un texto" en otras filas quedan vacíos (las invitaciones que mandó siguen vigentes); el enlace con Google se va con la cuenta, así que esa cuenta de Google y el mail quedan libres para volver a usarse (por ejemplo, se puede invitar de nuevo a la persona); su sesión abierta deja de funcionar al instante. El lugar se libera solo (los lugares son los usuarios activos de la institución) y la institución nunca se borra ni se desactiva por esto. No hay nada que configurar: sin migración y sin claves nuevas en `.env`.
- Si un usuario queda bloqueado tras 5 logins fallidos, puede reintentar a los 15 minutos, o un admin puede resetearle la contraseña.
- La duración de las sesiones y el bloqueo se configuran desde el `.env` (`ACCESS_TOKEN_TTL_MINUTES`, `SESSION_IDLE_TTL_HOURS`, `SESSION_ABSOLUTE_TTL_DAYS`, `LOGIN_MAX_FAILED_ATTEMPTS`, `LOGIN_LOCKOUT_MINUTES`; defaults en [`DATA_FLOW.es.md`](DATA_FLOW.es.md)). Después hay que recrear la API con `make api`. Las sesiones ya emitidas conservan la duración con la que se crearon.
- Si la API arranca sin ningún admin activo, deja un aviso en el log con el comando para crearlo.

## 7. Registro Público y Mail

**Qué hace.** Cualquier persona puede crear una cuenta `viewer` en `/register` (usuario, mail, contraseña y aceptación de los términos). La cuenta no puede entrar hasta que la persona abre el link de un solo uso que se le manda por mail (vale 24 h). Se entra con el usuario o con el mail, y quien olvidó su contraseña la recupera en `/forgot` (el link vale 60 min; al cambiarla se cierran todas las sesiones abiertas y se levanta un bloqueo). **Viene apagado por defecto.**

### 7.1 Configuración

Todo va en el `.env` (comentado en `.env.example`); docker compose se lo pasa a la API con estos valores por defecto. Después hay que recrear la API con `make api`.

| Variable | Default | Significado |
|----------|---------|-------------|
| `REGISTRATION_ENABLED` | `false` | Interruptor general del registro |
| `PUBLIC_BASE_URL` | vacío | Dirección pública del sitio, usada en los links de los mails (sin barra final) |
| `MAIL_HOST` | vacío | Servidor SMTP |
| `MAIL_PORT` | `587` | Puerto SMTP (en general 587 con STARTTLS, 465 con SSL) |
| `MAIL_USER` / `MAIL_PASSWORD` | vacío | Usuario y contraseña del SMTP; dejar `MAIL_USER` vacío si el servidor no pide ninguno |
| `MAIL_FROM` | vacío | Dirección del remitente |
| `MAIL_STARTTLS` | `true` | Cifra la conexión subiéndola a TLS (puerto 587). Se ignora si `MAIL_USE_SSL` está activo |
| `MAIL_USE_SSL` | `false` | Cifrada desde el primer byte (puerto 465) |
| `TERMS_REQUIRED` | `false` | Pedir que la persona acepte los términos y la política de privacidad en el registro (casilla y links). Apagado por defecto: el formulario no muestra ninguno. Encenderlo antes de abrir el registro al público (ver §7.3) |
| `TERMS_URL` / `PRIVACY_URL` | vacío | Links que muestra el formulario de registro cuando `TERMS_REQUIRED=true`; los textos los provee el observatorio |
| `EMAIL_VERIFY_TTL_HOURS` | `24` | Vida del link de verificación. Una cuenta pendiente solo puede ser reemplazada por un registro nuevo pasado este tiempo |
| `PASSWORD_RESET_TTL_MINUTES` | `60` | Vida del link de recupero |
| `INVITATION_TTL_DAYS` | `7` | Vida del link de una invitación (spec E). Opcional |
| `MAIL_MAX_PER_HOUR` | `3` | Mails que puede recibir una cuenta por hora (cuentan todos los tipos) |
| `MAIL_MIN_INTERVAL_SECONDS` | `60` | Tiempo mínimo entre dos mails a una misma cuenta |
| `MAIL_MAX_GLOBAL_PER_HOUR` | `200` | Mails de todo el sitio por hora; pasado ese número solo sale el recupero de contraseña |
| `MAIL_MAX_GLOBAL_PER_DAY` | `1500` | Mails de todo el sitio por día; mantenerlo por debajo del límite diario del proveedor de SMTP (Gmail Workspace: unos 2.000) |

Cuando un tope frena un mail, la API no envía nada y responde exactamente igual que si lo hubiera enviado, así que la respuesta nunca revela si una cuenta existe.

### 7.2 Cuándo está disponible

- **El registro** necesita `REGISTRATION_ENABLED=true` **y** `MAIL_HOST`, `MAIL_FROM` y `PUBLIC_BASE_URL`; solo con `TERMS_REQUIRED=true` necesita además `TERMS_URL` y `PRIVACY_URL`.
- **La verificación y el recupero de contraseña** solo necesitan la configuración del mail (`MAIL_HOST`, `MAIL_FROM`, `PUBLIC_BASE_URL`).
- Si `REGISTRATION_ENABLED=true` pero falta algo, la API dice qué en su log al arrancar y el registro queda apagado (el endpoint responde 503 y el login no ofrece "Crear cuenta").

### 7.2b Cómo se ven los mails

Los tres mails de la cuenta (verificar el mail, recuperar la contraseña, "ya tenés una cuenta") comparten un mismo diseño: el logo del observatorio, el título, el texto, un botón y un aviso al pie.

- **El link está solo dentro del botón.** El cuerpo del mail en HTML nunca escribe la dirección, así que el token de un solo uso no se ve; debajo del botón solo nombra la página del sitio donde se puede pedir un mail nuevo (sin token). La **versión en texto plano** del mail, que solo muestran los programas que no leen HTML, conserva el link completo porque ahí no hay botón.
- **No responder.** El remitente se ve como **"WebMet25 (no responder)"** con la dirección de `MAIL_FROM` (si `MAIL_FROM` ya trae un nombre, `Nombre <dirección>`, se respeta ese nombre). Todos los mails terminan con "este es un mensaje automático, no respondas; si necesitás ayuda escribinos a info@ohmc.ar". Llevan `Auto-Submitted: auto-generated` y `X-Auto-Response-Suppress: All` (las respuestas automáticas de vacaciones no los contestan) y **no llevan `Reply-To`**.
- **El logo viaja dentro del mail** (una imagen en línea de unos 30 KB, `api/app/mail/assets/ohmc-logo.png`), no como un link al sitio, porque los programas de correo suelen bloquear las imágenes remotas hasta que la persona las autoriza.
- **Para verlos:** en desarrollo, Mailpit muestra cada mail en http://localhost:8025 (ver §7.4).

### 7.2c Editar los textos de los mails

El admin general puede cambiar el **texto** de los cuatro mails (verificar el mail, recuperar la contraseña, "ya tenés una cuenta" y la invitación a una institución) desde **panel de admin, Configuración, Textos de los mails**, sin tocar el código ni redeployar. Solo el admin general puede abrirlo o cambiarlo (un admin de institución o un lector recibe 403).

- **Qué se puede cambiar:** el asunto, el título, los párrafos (separados por una línea en blanco), el texto del botón, el pie y el texto del link alternativo. **Qué no:** el logo, los colores y el diseño, el botón y su link (vienen del código y del token) y el aviso "no respondas a este mail".
- **Marcas:** el texto puede usar marcas que se reemplazan al enviar, por ejemplo `{usuario}`, `{horas}` o `{institucion}`. La pantalla muestra las que acepta cada mail (los botones las insertan donde está el cursor). Una marca que el mail no tiene se rechaza al guardar, así un error de tipeo nunca llega a un mail real. Cualquier otra cosa con llaves queda como texto.
- **Vista previa:** la pantalla muestra el mail con datos de ejemplo mientras se escribe, armado por el mismo código que arma el mail real. No envía ni guarda nada. **Restaurar original** vuelve al texto escrito en el código.
- **Dónde se guarda:** tabla `mail_templates`, una fila por cada mail personalizado (queda registrado quién y cuándo). Sin fila el mail sale con su texto original, así que un deploy no cambia ningún mail. Si no se puede leer la tabla, el mail sale con el texto original y el error queda en el log.
- **Seguridad:** el texto es texto plano (el HTML que se escriba se muestra como texto, no se ejecuta), el asunto no puede tener saltos de línea y la base solo se consulta con parámetros enlazados. La vista previa se ve en un iframe sin permisos.
- **Despliegue:** reconstruir API y frontend. `db-init` aplica la migración `f7a8b9c0d1e2` (tabla `mail_templates`). Sin claves nuevas en `.env`.

### 7.3 Encenderlo en producción

1. Si hay un proxy delante de nginx, configurar antes `set_real_ip_from` / `real_ip_header`. Los límites de estos endpoints (10 pedidos por minuto por IP) son por IP del cliente: sin la IP real todos los visitantes comparten la del proxy y la cuota se agota para todos.
2. Configurar SPF y DKIM del dominio del remitente, o los mails caen en spam.
3. Gmail / Workspace: usar una contraseña de aplicación (no la de la cuenta) y tener en cuenta los topes diarios (unos 500 y 2.000 mails).
4. Conseguir los términos y la política de privacidad (los textos los provee el observatorio, idealmente revisados por su área legal), poner sus direcciones en `TERMS_URL` y `PRIVACY_URL` y activar `TERMS_REQUIRED=true`. Viene apagado para poder probar el registro antes de que existan los textos, pero **antes de abrirlo al público** hay que mostrárselos a las personas: es el aviso y el consentimiento que pide la ley de datos personales (Ley 25.326) cuando se recolectan datos. Mientras esté apagado, la API lo avisa en su log al arrancar y no se registra ninguna aceptación (`terms_accepted_at` queda vacío).
5. Completar `MAIL_*`, `PUBLIC_BASE_URL` y poner `REGISTRATION_ENABLED=true`, y desplegar con `make up` (o `make db-init` y `make api`). `db-init` aplica la migración pendiente de la base; si dos usuarios tienen el mismo mail, falla con un mensaje claro que los lista. Hay que corregir esas filas y volver a correrlo.
6. Para apagarlo de inmediato: `REGISTRATION_ENABLED=false` y `make api`. Las cuentas ya creadas siguen funcionando.

### 7.4 Desarrollo

El stack de desarrollo tiene un buzón local, **Mailpit**: `http://localhost:8025` (accesible solo desde esta máquina). La API principal de ese stack ya tiene el registro encendido y envía ahí, así que nada sale de tu computadora. Los tests de caja negra y de punta a punta usan su propia API (`api-e2e`) con el mismo buzón; ver [`E2E_TESTING.es.md`](E2E_TESTING.es.md).

### 7.5 Pendiente conocido

**No hay limpieza automática** de las cuentas sin verificar ni de las filas vencidas de `email_tokens`. Una cuenta sin verificar se reemplaza cuando alguien se registra de nuevo con su usuario o mail una vez vencido su link (24 h), y hasta entonces conserva ese usuario. Los tokens vencidos se acumulan hasta que se escriba un job de limpieza. (Los logins viejos de `user_sessions` se borran en cada login de ese usuario; ver §6.)

---

## 8. Servir una copia bajo un prefijo (base path)

Cuando dos copias del sitio tienen que compartir un hostname (por ejemplo en stage, la de Javi en `/` y la de Nacho en
`/nacho/`), el proxy de adelante decide por prefijo y lo **saca**. La imagen no cambia: la copia se entera de su
prefijo por el header `X-Forwarded-Prefix` (ver `docs/DATA_FLOW.es.md`, "Base path").

Caddyfile del proxy (en stage: `webmet_caddy`, bloque `:8080`):

```
:8080 {
  bind 127.0.0.1
  encode zstd gzip

  # La copia bajo /nacho/: saca el prefijo y le avisa a su nginx.
  redir /nacho /nacho/
  handle_path /nacho/* {
    reverse_proxy 127.0.0.1:8081 {
      header_up X-Forwarded-Prefix /nacho
    }
  }

  # Todo lo demás: la copia en la raíz. Un cliente no puede inventar un prefijo acá.
  handle {
    request_header -X-Forwarded-Prefix
    reverse_proxy 127.0.0.1:80
  }
}
```

Con `admin off`, se aplica con `docker restart <contenedor de caddy>` (`caddy reload` necesita la API de admin).

En el `.env` de la copia bajo el prefijo:

- `FRONTEND_PORT` = el puerto al que apunta el Caddyfile (`8081` arriba).
- `PUBLIC_BASE_URL=https://<host>/nacho`, para que los links de los mails lleven el prefijo.
- `ALLOWED_ORIGINS` = el mismo origen público que la otra copia (`https://<host>`): el origen no tiene path.

Cada copia mantiene sus propias sesiones (los nombres de cookie llevan el prefijo), así que un mismo navegador puede
estar logueado en las dos.

## 9. Vistas de radar único por usuario

El mapa muestra todos los radares a todos los usuarios con sesión, pero la **página de un radar** (`radar.html`, a la que se llega con el botón › junto a cada radar) necesita un permiso. El admin ve siempre todos los radares con `detail_view_enabled` encendido; cualquier otra persona ve solo los radares que el admin le asignó.

- **Asignarlas:** panel de admin, **Usuarios**, botón **Vistas** en la fila del usuario. Se tilda "Todas" (todos los radares, también los que se agreguen después) o se eligen radares. Solo se listan los radares con la vista de detalle habilitada. Al guardar se reemplaza la lista entera.
- **Qué ve la persona:** el botón › aparece solo junto a los radares que puede abrir. Si abre `radar.html?code=...` a mano, ve "No tenés acceso a la vista de este radar" y vuelve al mapa a los 5 segundos.
- **Qué no cubre:** el permiso abre solo la página. Los endpoints de datos son los mismos que usa el mapa, así que todos siguen viendo todos los radares en el mapa principal.
- **Apagar una vista** (`detail_view_enabled`) la oculta para todos, también para el admin, sin tocar la lista de nadie.
- **Borrar un radar** borra los permisos que lo nombran.
- **Las cuentas nuevas no tienen vistas.** Eso incluye las cuentas creadas por el registro y por "Continuar con Google". Las personas que ya existían antes de esta versión también empiezan sin ninguna.

**Nota de despliegue:** después de aplicar esta versión, **nadie salvo el admin puede abrir la vista de un radar** hasta que el admin se la asigne. Conviene asignar las vistas antes de anunciar el cambio, o avisar a los usuarios. La migración (`c4d5e6f7a8b9`, tabla `permissions`) la aplica `db-init` en el próximo `docker compose up -d --build`; no necesita ninguna clave nueva en el `.env`.

### 9.1 Herramienta de seguimiento de tormentas

El seguimiento de tormentas (botón de la vista de un radar) es una **herramienta** que se da o no, como las vistas pero de sí/no: el admin general se la da a una institución (al crearla, o después con el botón **Herramientas** de su fila) y el admin de la institución se la da a sus usuarios desde su panel, solo mientras la institución la tenga. Cada usuario la usa en cada vista de radar que puede abrir. Sacarle la herramienta a una institución se la saca a todos sus miembros al instante; sacar la vista de un radar solo quita el tracking de ese radar. Las invitaciones llevan la elección (la de un lector); sin elección la persona arranca con una copia de la institución. nginx lo exige: todo `/api/tracking/` y la página `/tracking` necesitan la herramienta (consulta `/_auth_tracking`), y las rutas por radar (`/api/tracking/radars/CÓDIGO/...`) necesitan la herramienta **y** la vista de ese radar (consulta `/_auth_tracking_radar`). Sin ella nginx responde 403 (la página vuelve al mapa).

**Nota de despliegue:** la migración `c8e1f4a7b2d9` (restricción de `permissions` + `invitations.tracking`) la aplica `db-init`. Después, **nadie tiene tracking**, ni siquiera quienes lo usan hoy: el admin general tiene que dárselo a las instituciones (y, si hace falta, a usuarios sin institución) desde **Herramientas**. Avisar a los usuarios antes de desplegar. Sin claves nuevas en `.env`.

## 10. Cuentas de empresa

> **Nombres.** En pantalla (panel de admin, panel de la institución, mapa, mensajes de la API) a la empresa se la llama **"institución"** (plural "instituciones"): sección "Instituciones", "Agregar institución", "Admin de institución", "Mi institución". En el código, la base de datos y las URLs conserva sus nombres (`organizations`, `org_admin`, `/api/v1/org`, `/empresa`). Los mensajes en español que manda la API también dicen "institución".

Una **empresa** (por ejemplo EPEC) es un grupo de usuarios con un **tope de lugares** y su propia lista de vistas de radar único. La crea el admin general; después un **admin de empresa** (rol `org_admin`) administra a los usuarios de la empresa desde `/empresa`, un panel propio.

- **Crear una empresa:** panel de admin, **Instituciones**, "Agregar institución": nombre, tope de lugares (usuarios activos, admins de empresa incluidos) y si está activa. En el mismo formulario se puede **elegir al admin de la empresa** (crear un usuario nuevo, elegir un lector que ya existe y no está en ninguna empresa, con una caja de búsqueda que filtra por usuario, nombre o mail, o dejarlo para después) y **asignar las vistas de radar** de la empresa. Todo se crea en un solo paso: si alguna parte se rechaza (nombre o usuario repetido, contraseña débil, un usuario que no se puede elegir, un radar inexistente) no se crea nada, ni la empresa. Un usuario existente pasa a ser el admin de la empresa: ocupa un lugar, se le cierran las sesiones y sus vistas propias se reemplazan por las de la empresa. No se ofrecen usuarios de otra empresa. El botón **Vistas** define la lista de vistas de radar de la empresa; **Usuarios** abre la sección de usuarios filtrada por esa empresa.
- **Nombrar a su admin:** panel de admin, **Usuarios**, "Agregar usuario", elegir la empresa y el rol "Admin de institución". Solo el admin general crea o cambia admins de empresa, y un admin de empresa nunca cambia de empresa (para moverlo, se crea una cuenta nueva).
- **Mover una cuenta existente:** panel de admin, **Usuarios**, editar un lector y cambiar el selector **Empresa** (solo el admin general; sirve para sumarlo a una empresa, pasarlo a otra o sacarlo con "Ninguna"). El formulario avisa qué va a pasar antes de guardar. Entrar a una empresa ocupa un lugar (409 si está llena o inactiva) y **reemplaza** las vistas de la cuenta por una copia de las de la empresa (sin intersección; si la persona tiene que ver más, hay que darle más vistas a la empresa); se le cierran las sesiones. Salir libera el lugar y le quita sus vistas de radar (las que le dio la institución); se le cierran las sesiones y la cuenta sigue activa. Cuando un admin de empresa intenta agregar un usuario o mail que ya existe, el panel le dice que le pida al admin general que sume esa cuenta a su empresa.
- **Qué puede hacer un admin de empresa** (desde el botón "Mi institución" de la franja de cuenta del mapa, o en `/empresa`): crear usuarios (entran como lectores de la empresa, con una contraseña inicial, y empiezan con las vistas de la empresa), editar nombre y mail, resetear contraseñas, cerrar sesiones, desvincular (dejan de ocupar lugar, pierden las vistas que les dio la institución y se les cierran las sesiones; la cuenta sigue activa y solo el admin general puede volver a sumarla), y achicar las vistas de radar de cada uno, siempre dentro de la lista de la empresa. No puede tocar a otros admins de empresa, a otras empresas ni entrar a `/admin`.
- **Lugares:** crear o reactivar un usuario de la empresa necesita un lugar libre (409 si no). Desactivar lo libera. Bajar el tope por debajo de los usuarios activos no desactiva a nadie: solo bloquea los usuarios nuevos.
- **Una institución con usuarios siempre tiene admin:** si tiene al menos un usuario **activo**, tiene que tener al menos un admin **activo** (puede haber varios; una institución sin usuarios puede no tener ninguno). Por eso la API responde 409 si bajás a lector, desactivás o desvinculás al único admin activo mientras queden otros usuarios activos, y si agregás, movés o reactivás a un lector en una institución sin admin activo (primero hay que crearle el admin). El admin general puede sacar a un admin en un solo paso: edita al admin y elige **Ninguna** en el selector de institución; vuelve a lector sin institución, libera su lugar, pierde sus vistas y se le cierran las sesiones. Las instituciones que ya incumplen la regla quedan como están.
- **Invitaciones por mail:** en lugar de crear la cuenta con una contraseña, un admin puede invitar a una persona por mail. El admin general lo hace al crear una institución (opción de admin **Invitar por mail**) o desde **panel de admin, Invitaciones** (admin de institución o lector); el admin de institución lo hace desde `/empresa`, **Agregar usuario, Invitar por mail** (siempre un lector de su institución, con las vistas de radar que marque, que tienen que estar dentro de la lista de su institución: si no, 403). La persona recibe un mail con un link (`/invitacion#token=...`, vale `INVITATION_TTL_DAYS`, 7 por defecto, y se usa una sola vez), lo abre y completa un formulario (usuario, nombre, contraseña) o usa **Google**, y entra con la sesión iniciada. Con Google se exige la cuenta del mail invitado: otra cuenta de Google se rechaza. Una **invitación pendiente reserva un lugar** (lugares libres = tope - usuarios activos - invitaciones pendientes) hasta que se acepta, se cancela o vence; los dos paneles listan las pendientes con **Reenviar** (un link nuevo, el anterior deja de funcionar) y **Cancelar**. Una invitación pendiente de otra institución responde 409; un lector solo se invita a una institución con admin activo. Las invitaciones necesitan el mail configurado (`MAIL_*`, `PUBLIC_BASE_URL`) pero **no** `REGISTRATION_ENABLED`, y cuentan para los mismos topes de envío que los demás mails (429 al pasarlos). Nunca se borran: las aceptadas, canceladas y vencidas quedan en la tabla `invitations` como registro.
- **Invitar a quien ya tiene cuenta:** no es un error. Quien invita recibe un **aviso** ("Ese mail ya tiene una cuenta: la invitación se envió igual") y el mail sale; las listas de pendientes muestran la marca "Ya tiene cuenta". Al abrir el link, la página le pregunta al servidor si el mail tiene cuenta (`account_exists`, calculado en ese momento) y, si la tiene, muestra un **inicio de sesión** en lugar del formulario de cuenta nueva (también Google). Para sumarse hacen falta el link Y una sesión de la cuenta de ese mail (otra cuenta recibe 403): el link solo no puede entrar a la cuenta de nadie. Todo se comprueba de nuevo al sumarse; la persona recibe las vistas de la invitación (reemplazan las que tenía), una sesión nueva reemplaza las viejas y entra directo a la app. A quién se puede invitar: a un lector sin institución (los dos que invitan); a un lector de OTRA institución solo el admin general (al aceptar la persona se mueve: sale de la vieja, su lugar allá se libera y pierde esas vistas), y un admin de institución recibe un 409 ("pedile al administrador general que la mueva"); una cuenta de admin de institución o de admin general, una desactivada, una que nunca verificó su mail o una que ya es de esa institución reciben un 409. Invitado como admin de institución por el admin general, un lector existente pasa a ser admin de esa institución. El endpoint público `POST /api/v1/invitations/accept-existing` está dentro del mismo límite de nginx que `details`, `accept` y `accept-google`. Sin migración y sin claves nuevas en `.env`.
- **Vistas de un miembro de la empresa** = su propia lista intersectada con la de la empresa, calculado en cada lectura: si el admin general le quita un radar a la empresa, todos sus miembros lo pierden al instante. Un admin de empresa ve la lista de la empresa.
- **Una empresa desactivada** bloquea a todos sus usuarios: no pueden entrar (con contraseña ni con Google) y sus sesiones abiertas dejan de funcionar.
- **Entrar con Google:** un admin de empresa puede usarlo (solo el admin general no). Si un admin (general o de institución) **cambia el mail** de una cuenta, se le quita el enlace con Google: el id de Google pertenece al mail viejo, así que esa cuenta de Google queda libre, y la persona enlaza el mail nuevo la próxima vez que use Google (se la encuentra por mail). Mientras tanto entra con contraseña (el admin puede resetearla, o sirve "Olvidé mi contraseña" porque el mail nuevo queda verificado).
- **Qué no cubre:** igual que las vistas por usuario, la lista de la empresa solo decide qué páginas de radar único se abren. Los endpoints de datos son los mismos para todos.

**Nota de despliegue:** la migración (`d5e6f7a8b9c0`: tablas `organizations`, `users.organization_id`, el rol `org_admin` y las filas de `permissions` que pertenecen a una empresa) la aplica `db-init` en el próximo `docker compose up -d --build`. No hay claves nuevas en el `.env`. Nadie pertenece a una empresa hasta que el admin general cree una, así que para los usuarios existentes no cambia nada.

## 11. Perfil de usuario

Cada usuario tiene una página de perfil, `/perfil`, con el mismo diseño del panel de admin. Muestra los datos de la
cuenta (usuario, nombre, mail, rol, empresa, alta, último ingreso) y los radares que puede abrir en la vista de radar
único; el admin de empresa ve además la tarjeta de su empresa (lugares y vistas).

- **Cómo llega cada rol:** el lector tiene un botón de perfil en la franja de cuenta del mapa (página `/perfil`). El
  admin general y el admin de empresa no tienen un botón extra: el perfil es una sección **dentro de su panel** ("Mi
  perfil" en el menú lateral: `admin#profile` y `empresa#perfil`), a la que llegan con el botón que ya tenían.
  `/perfil` los manda a esa sección.
- **Qué se puede editar:** solo el nombre. Usuario y mail son de solo lectura acá (un admin sí puede cambiar un mail
  desde el panel de admin).
- **Todavía no incluye:** foto de perfil (el avatar son siempre las iniciales). El diseño quedó guardado en la spec.

**Nota de despliegue:** nada especial. Sin migración, sin volumen nuevo, sin claves nuevas en el `.env`. Se aplica
con `docker compose up -d --build`.

---

**Versión del Documento:** 1.2.0  
**Última Actualización:** 27 de octubre de 2026
