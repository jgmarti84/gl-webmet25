# Makefile de gl-webmet25
#
# Atajos para el docker-compose.yml.
#
# Servicios del compose: redis, radar_db, db-init, indexer, api, frontend
#
# Regla general: "make <servicio>" reconstruye y recrea SOLO ese servicio
# (--no-deps evita tocar sus dependencias).

COMPOSE_BASE = docker compose

# Stack de desarrollo: el compose normal + docker-compose.devcontainer.yml encima.
DEV_COMPOSE = $(COMPOSE_BASE) -f docker-compose.yml -f docker-compose.devcontainer.yml

# "make <objetivo> DEV=1" aplica el override a CUALQUIER objetivo.
ifeq ($(DEV),1)
COMPOSE ?= $(DEV_COMPOSE)
else
COMPOSE ?= $(COMPOSE_BASE)
endif

# Los nombres de servicio coinciden con carpetas (api, indexer, frontend): sin
# .PHONY, make diria "is up to date" y no haria nada.
.PHONY: help up down stop ps config build \
        api indexer frontend db redis db-init shared rebuild \
        logs logs-api logs-indexer logs-frontend logs-db logs-redis \
        psql health stats dev-up dev-down test test-api test-indexer test-e2e \
        db-check db-seed db-sync db-migrate create-admin reset-password test-auth

.DEFAULT_GOAL := help

help:
	@echo Uso: make [objetivo]
	@echo ----------------------------------------
	@echo Stack completo
	@echo   up - Construye y levanta todo
	@echo   down - Baja y elimina los contenedores
	@echo   stop - Detiene sin eliminar
	@echo   ps - Estado de los servicios
	@echo   build - Solo construye las imagenes
	@echo   config - Valida el compose y el .env
	@echo ----------------------------------------
	@echo Un solo servicio - reconstruye y recrea solo ese
	@echo   api - Reconstruye la API
	@echo   indexer - Reconstruye el indexer
	@echo   frontend - Reconstruye el frontend
	@echo   db - Levanta la base de datos
	@echo   redis - Levanta Redis
	@echo   db-init - Corre init y seed de la base una vez
	@echo   shared - Reconstruye api e indexer - cambios en database/radar_db
	@echo   rebuild-SERVICIO - Reconstruye SIN cache y con imagen base nueva, por ejemplo make rebuild-api
	@echo   rebuild - Lo mismo para todo el stack, es lento
	@echo ----------------------------------------
	@echo Otros servicios sin reconstruir
	@echo   restart-SERVICIO - Reinicia sin reconstruir, por ejemplo make restart-api o restart-radar_db
	@echo ----------------------------------------
	@echo Logs - Ctrl+C para salir
	@echo   logs - todos, y logs-api logs-indexer logs-frontend logs-db logs-redis
	@echo ----------------------------------------
	@echo Utilidades
	@echo   health - Consulta /health de la API
	@echo   stats - Uso de CPU y memoria de los contenedores
	@echo   psql - Abre psql en la base
	@echo   shell-SERVICIO - Abre una shell dentro, por ejemplo make shell-api o shell-indexer
	@echo ----------------------------------------
	@echo Base de datos
	@echo   db-check - Verifica la conexion
	@echo   db-seed - Carga datos iniciales - solo inserta lo que falta
	@echo   db-sync - Sincroniza el seed completo - actualiza existentes
	@echo   db-migrate - Aplica migraciones pendientes
	@echo   create-admin U=usuario - Crea un admin, pide la contrasena por consola
	@echo   reset-password U=usuario - Cambia la contrasena de un usuario y cierra sus sesiones
	@echo ----------------------------------------
	@echo Desarrollo y tests, usa docker-compose.devcontainer.yml encima
	@echo   dev-up - Levanta el stack de desarrollo, el stack de test aislado y el contenedor de tests
	@echo   dev-down - Baja ese stack, usalo en vez de down
	@echo   test - Corre todos los tests dentro del contenedor tests
	@echo   test-api  test-indexer  test-e2e - Solo una parte de los tests
	@echo   test-auth - Tests de usuarios y autenticacion
	@echo   Cualquier objetivo acepta DEV=1, por ejemplo make logs DEV=1

# ---------------------------------------------------------------------------
# Stack completo
# ---------------------------------------------------------------------------
up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

stop:
	$(COMPOSE) stop

ps:
	$(COMPOSE) ps -a

build:
	$(COMPOSE) build

config:
	$(COMPOSE) config -q

# ---------------------------------------------------------------------------
# Un solo servicio
# ---------------------------------------------------------------------------
api:
	$(COMPOSE) up -d --build --no-deps api

indexer:
	$(COMPOSE) up -d --build --no-deps indexer

frontend:
	$(COMPOSE) up -d --build --no-deps frontend

# La base y Redis usan imagenes ya hechas: no hay nada que reconstruir.
db:
	$(COMPOSE) up -d --no-deps radar_db

redis:
	$(COMPOSE) up -d --no-deps redis

# db-init no es un servicio permanente: corre init + seed y termina.
db-init:
	$(COMPOSE) up --build --no-deps db-init

# database/radar_db se copia dentro de las imagenes de api, indexer y db-init.
# Si tocas modelos o seeds, reconstrui los que dependen de eso.
shared:
	$(COMPOSE) up -d --build --no-deps api indexer

# Reconstruccion limpia: sin cache de capas (--no-cache) y bajando la imagen base
# de nuevo (--pull). Es lenta. Usala cuando pip o apt pueden traer versiones nuevas
# o cuando el cache de Docker se comporta raro. Ejemplo: make rebuild-api
rebuild-%:
	$(COMPOSE) build --no-cache --pull $*
	$(COMPOSE) up -d --no-deps $*

rebuild:
	$(COMPOSE) build --no-cache --pull
	$(COMPOSE) up -d

# Reinicio sin reconstruir (por ejemplo tras cambiar el .env). Ejemplo: make restart-api
restart-%:
	$(COMPOSE) restart $*

# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------
logs:
	$(COMPOSE) logs -f --tail=100

logs-api:
	$(COMPOSE) logs -f --tail=100 api

logs-indexer:
	$(COMPOSE) logs -f --tail=100 indexer

logs-frontend:
	$(COMPOSE) logs -f --tail=100 frontend

logs-db:
	$(COMPOSE) logs -f --tail=100 radar_db

logs-redis:
	$(COMPOSE) logs -f --tail=100 redis

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
health:
	curl http://localhost:8000/health

stats:
	docker stats --no-stream

psql:
	$(COMPOSE) exec radar_db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

# Abre una shell dentro del contenedor. Ejemplo: make shell-api
shell-%:
	$(COMPOSE) exec $* sh

# ---------------------------------------------------------------------------
# Base de datos (usa "run", no "exec": db-init termina despues de arrancar)
# ---------------------------------------------------------------------------
db-check:
	$(COMPOSE) run --rm db-init python -m radar_db.manage check

db-seed:
	$(COMPOSE) run --rm db-init python -m radar_db.manage seed

db-sync:
	$(COMPOSE) run --rm db-init python -m radar_db.manage sync

db-migrate:
	$(COMPOSE) run --rm db-init python -m radar_db.manage migrate upgrade

# Comandos de usuarios que se corren en el servidor (piden la contrasena por consola).
create-admin:
	$(COMPOSE) run --rm db-init python -m radar_db.manage create-admin --username $(U)

reset-password:
	$(COMPOSE) run --rm db-init python -m radar_db.manage reset-password --username $(U)

# ---------------------------------------------------------------------------
# Desarrollo y tests (docker-compose.devcontainer.yml encima del compose normal)
# ---------------------------------------------------------------------------
# Lista de servicios tomada de docs/E2E_TESTING.md. Deja afuera indexer y frontend,
# que en este override quedan dormidos con "tail -f /dev/null".
# Levanta el stack de desarrollo (api, frontend-v2 sobre radar_prod_db), la base de test de tests/auth y
# tests/indexer, y el stack aislado de tests/api y tests/e2e (radar_db_e2e, api-e2e, frontend-e2e, indexer-e2e).
dev-up:
	$(DEV_COMPOSE) up -d --build radar_db redis db-init api frontend-v2 radar_db_test db-init-test radar_db_e2e db-init-e2e api-e2e frontend-e2e prefix-proxy-e2e indexer-e2e tests

# Usar este y no "down": los servicios nuevos del override (tests, frontend-v2,
# radar_db_test) no se bajan sin pasar el archivo devcontainer.
dev-down:
	$(DEV_COMPOSE) down

test:
	$(DEV_COMPOSE) exec tests pytest

test-api:
	$(DEV_COMPOSE) exec tests pytest tests/api -v

test-indexer:
	$(DEV_COMPOSE) exec tests pytest tests/indexer -v

test-e2e:
	$(DEV_COMPOSE) exec tests pytest tests/e2e -v

test-auth:
	$(DEV_COMPOSE) exec tests pytest tests/auth -v
