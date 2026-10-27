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
- Los demás usuarios se gestionan desde el panel de administración (**Usuarios**): crear, cambiar rol, activar/desactivar, resetear contraseña, cerrar sesiones. Los usuarios nunca se borran, solo se desactivan.
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
| `TERMS_URL` / `PRIVACY_URL` | vacío | Links que muestra el formulario de registro; los textos los provee el observatorio |
| `EMAIL_VERIFY_TTL_HOURS` | `24` | Vida del link de verificación. Una cuenta pendiente solo puede ser reemplazada por un registro nuevo pasado este tiempo |
| `PASSWORD_RESET_TTL_MINUTES` | `60` | Vida del link de recupero |
| `MAIL_MAX_PER_HOUR` | `3` | Mails que puede recibir una cuenta por hora (cuentan todos los tipos) |
| `MAIL_MIN_INTERVAL_SECONDS` | `60` | Tiempo mínimo entre dos mails a una misma cuenta |

Cuando un tope frena un mail, la API no envía nada y responde exactamente igual que si lo hubiera enviado, así que la respuesta nunca revela si una cuenta existe.

### 7.2 Cuándo está disponible

- **El registro** necesita `REGISTRATION_ENABLED=true` **y** `MAIL_HOST`, `MAIL_FROM`, `PUBLIC_BASE_URL`, `TERMS_URL` y `PRIVACY_URL`.
- **La verificación y el recupero de contraseña** solo necesitan la configuración del mail (`MAIL_HOST`, `MAIL_FROM`, `PUBLIC_BASE_URL`).
- Si `REGISTRATION_ENABLED=true` pero falta algo, la API dice qué en su log al arrancar y el registro queda apagado (el endpoint responde 503 y el login no ofrece "Crear cuenta").

### 7.3 Encenderlo en producción

1. Si hay un proxy delante de nginx, configurar antes `set_real_ip_from` / `real_ip_header`. Los límites de estos endpoints (10 pedidos por minuto por IP) son por IP del cliente: sin la IP real todos los visitantes comparten la del proxy y la cuota se agota para todos.
2. Configurar SPF y DKIM del dominio del remitente, o los mails caen en spam.
3. Gmail / Workspace: usar una contraseña de aplicación (no la de la cuenta) y tener en cuenta los topes diarios (unos 500 y 2.000 mails).
4. Tener `TERMS_URL` y `PRIVACY_URL` (los textos los provee el observatorio).
5. Completar `MAIL_*`, `PUBLIC_BASE_URL` y poner `REGISTRATION_ENABLED=true`, y desplegar con `make up` (o `make db-init` y `make api`). `db-init` aplica la migración pendiente de la base; si dos usuarios tienen el mismo mail, falla con un mensaje claro que los lista. Hay que corregir esas filas y volver a correrlo.
6. Para apagarlo de inmediato: `REGISTRATION_ENABLED=false` y `make api`. Las cuentas ya creadas siguen funcionando.

### 7.4 Desarrollo

El stack de desarrollo tiene un buzón local, **Mailpit**: `http://localhost:8025` (accesible solo desde esta máquina). La API principal de ese stack ya tiene el registro encendido y envía ahí, así que nada sale de tu computadora. Los tests de caja negra y de punta a punta usan su propia API (`api-e2e`) con el mismo buzón; ver [`E2E_TESTING.es.md`](E2E_TESTING.es.md).

### 7.5 Pendiente conocido

**No hay limpieza automática** de las cuentas sin verificar ni de las filas vencidas de `email_tokens`. Una cuenta sin verificar se reemplaza cuando alguien se registra de nuevo con su usuario o mail una vez vencido su link (24 h), y hasta entonces conserva ese usuario. Los tokens vencidos se acumulan hasta que se escriba un job de limpieza. (Los logins viejos de `user_sessions` se borran en cada login de ese usuario; ver §6.)

---

**Versión del Documento:** 1.2.0  
**Última Actualización:** 27 de octubre de 2026
