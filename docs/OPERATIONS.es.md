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

# Vaciar la caché en proceso de colormaps (tras editar colormaps en el panel de administración)
curl -X POST http://localhost/api/v1/colormap/cache/invalidate
```

---

**Versión del Documento:** 1.0.0  
**Última Actualización:** 8 de julio de 2026
