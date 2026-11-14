# Decisiones de diseño — cuentas, acceso y operación

Este documento registra **por qué** las funciones de cuentas, permisos y acceso de WebMet25 están hechas como están:
las decisiones que no se pueden leer en el código, las alternativas que se descartaron y lo que cuesta cada elección.
Está pensado para quien tome el proyecto. Qué hace el sistema y cómo se opera está en
[`DATA_FLOW.md`](DATA_FLOW.md), [`COMPONENTS.md`](COMPONENTS.md) y [`OPERATIONS.md`](OPERATIONS.md); algunos puntos se
repiten acá a propósito, vistos desde el lado del "por qué". La versión en inglés está en
[`DESIGN_DECISIONS.md`](DESIGN_DECISIONS.md).

Cada entrada tiene: **Contexto** (el problema), **Decisión**, **Alternativas** (y por qué no) y **Consecuencias** (qué se
gana, qué se pierde, qué queda para después). Las decisiones que después cambiaron lo dicen.

**Contenido**

1. [Autenticación y sesiones](#1-autenticación-y-sesiones)
2. [Login obligatorio](#2-login-obligatorio)
3. [Registro público y mails](#3-registro-público-y-mails)
4. [Ingreso con Google](#4-ingreso-con-google)
5. [Roles y permisos](#5-roles-y-permisos)
6. [Instituciones (cuentas de empresa)](#6-instituciones-cuentas-de-empresa)
7. [Invitaciones](#7-invitaciones)
8. [Borrar usuarios e instituciones](#8-borrar-usuarios-e-instituciones)
9. [Perfil y textos de los mails](#9-perfil-y-textos-de-los-mails)
10. [Herramienta de seguimiento de tormentas](#10-herramienta-de-seguimiento-de-tormentas)
11. [Infraestructura y rendimiento](#11-infraestructura-y-rendimiento)
12. [Tests](#12-tests)
13. [Interfaz](#13-interfaz)
14. [Pendientes conocidos](#14-pendientes-conocidos)

---

## 1. Autenticación y sesiones

### 1.1 Access token JWT corto más un refresh token que rota, los dos en cookies `HttpOnly`

- **Contexto:** el sitio solo tenía Basic Auth de nginx en el panel de admin. Hacían falta usuarios y sesiones.
- **Decisión:** un JWT firmado de 30 minutos (HS256, PyJWT) como cookie de acceso, y un refresh token opaco que rota
  en cada uso, los dos `HttpOnly`, `Secure` y `SameSite=Strict`. Una sesión muere a las 48 h sin uso y a los 7 días
  como máximo. El frontend renueva el access token solo, un poco antes de que venza.
- **Alternativas:** tokens en `localStorage` (cualquier script los lee, así que un XSS roba la sesión); solo sesiones
  del lado del servidor (más simple, pero de todos modos ya se iba a leer la base en cada pedido por otro motivo, ver
  1.2, así que el JWT sobre todo ahorra trabajo y permite chequear los tiles sin base, ver 11.2).
- **Consecuencias:** ningún token es accesible desde JavaScript. El primer diseño tenía 15 minutos; se subió a 30 para
  reducir a la mitad los refresh, que son la operación de auth más cara (bloquea y escribe una fila).

### 1.2 Cada pedido autenticado lee el usuario de la base

- **Contexto:** un JWT sigue siendo válido hasta que vence. Desactivar a alguien o resetearle la contraseña tiene que
  cortar el acceso en el momento, no hasta 30 minutos después.
- **Decisión:** después de verificar la firma, cada pedido carga el usuario (una lectura por clave primaria) y compara
  `is_active` y `token_version`. Subir `token_version` invalida al instante todos los access tokens de ese usuario.
- **Alternativas:** confiar solo en el JWT (más barato, pero la revocación llegaría tarde); cachear el usuario
  (complejidad sin evidencia de que haga falta).
- **Consecuencias:** una consulta chica por pedido. La única excepción son los tiles del mapa base (11.2). Los permisos
  tampoco van en el JWT (5.5).

### 1.3 Una fila de `user_sessions` por login, con detección de token robado

- **Contexto:** la primera versión escribía una fila por refresh, así que la tabla crecía rápido, y un refresh token
  robado se podía usar sin que nadie se enterara.
- **Decisión:** el refresh token es `<id del login>.<secreto>`; cada refresh rota el secreto **en la misma fila**.
  Presentar un secreto viejo de ese login (reuso) cierra el login y sube `token_version`, lo que además mata los access
  tokens del ladrón. Una ventana de 10 segundos acepta el secreto anterior para que dos pestañas que renuevan a la vez
  reciban una respuesta de "carrera de refresh" en vez de quedar deslogueadas. Mientras se rota, la fila se bloquea con
  `SELECT ... FOR UPDATE`. Los logins cerrados se borran a los 90 días, cuando ese usuario vuelve a loguearse.
- **Alternativas:** un id de familia más una fila por token (lo que había; más filas, la misma detección con más
  trabajo); no detectar el reuso (un token robado sigue andando hasta 7 días).
- **Consecuencias:** un ladrón y el usuario real no pueden mantener sesión los dos: el primero que reusa un token viejo
  la cierra. La limpieza no necesita un job programado. El log de auditoría (`auth.sessions`) nunca contiene tokens.

### 1.4 Guardado y política de contraseñas

- **Decisión:** Argon2id (con `pwdlib`); al menos 10 caracteres con un carácter especial; un reseteo por mail no puede
  reusar la contraseña actual. 5 logins fallidos bloquean la cuenta 15 minutos. La política se aplica al crear o
  cambiar una contraseña, no al loguear, así que las cuentas con una contraseña anterior más débil siguen entrando.
- **Alternativas:** se evitaron `passlib` y `python-jose` porque están poco mantenidas.
- **Consecuencias:** un atacante no puede bloquear una cuenta para siempre; quien queda bloqueado espera o le pide a un
  admin.

### 1.5 El primer admin sale del `.env`; un admin no se resetea su propia contraseña desde el panel

- **Decisión:** `db-init` crea el primer admin con `ADMIN_USERNAME`/`ADMIN_PASSWORD` solo si no hay usuarios. La
  contraseña de un admin se cambia en el servidor (`make reset-password`).
- **Por qué:** `make up` deja un sistema usable sin pasos manuales, y apoderarse de una cuenta de admin requiere acceso
  al servidor, no solo una sesión robada.

### 1.6 Roles como texto con un `CHECK`, no un `ENUM` de PostgreSQL

- **Por qué:** agregar un rol después (que pasó: `org_admin`) es cambiar un constraint, no un `ALTER TYPE`, que es
  incómodo en las migraciones.

---

## 2. Login obligatorio

### 2.1 Todo el sitio pide sesión; nginx cuida las páginas, la API cuida los datos

- **Contexto:** el mapa y la API eran públicos.
- **Decisión:** todos los routers de datos de la API piden sesión. nginx le pregunta a la API (`auth_request` a
  `/api/v1/auth/check`) antes de servir cada página HTML, así que sin sesión el navegador nunca recibe la página. Los
  estáticos (`.js`, `.css`, imágenes) siguen públicos.
- **Alternativas:** proteger las páginas solo en JavaScript (la página aparecería un instante y se podría leer);
  proteger también los estáticos (una lectura más de la base por archivo, sin proteger nada: no tienen datos).
- **Consecuencias:** la protección real es la API, así que saltear nginx (por ejemplo por el puerto 8000, que escucha
  solo en localhost) no da nada.

### 2.2 El login se sirve "en el lugar"

- **Decisión:** una URL protegida sin sesión responde con la página de login en esa misma URL (estado 401); después de
  loguearse, la página se recarga.
- **Por qué:** nginx no puede armar de forma segura un parámetro `?next=` con una URL que tenga `&`. Servir en el lugar
  conserva la URL original sin codificar nada.

### 2.3 Los proxies de tiles del mapa base también están cerrados

- **Por qué:** un proxy abierto a OpenStreetMap rompería su política de uso y podría hacer que bloqueen la IP del
  servidor.

---

## 3. Registro público y mails

### 3.1 El registro está apagado por defecto y necesita sus piezas listas

- **Decisión:** `REGISTRATION_ENABLED=false` por defecto; solo se enciende si el mail está configurado y, con
  `TERMS_REQUIRED=true`, también las URLs de términos y privacidad. Las invitaciones (7) andan aunque el registro esté
  apagado.
- **Por qué:** abrir el registro al público es una decisión de la institución (textos legales, reputación del
  remitente, IP real del cliente detrás del proxy), no un efecto secundario de un deploy.

### 3.2 La cuenta se crea al registrarse, inactiva hasta verificar el mail

- **Decisión:** la cuenta existe enseguida (reserva el usuario) pero no puede entrar hasta abrir el link del mail. Una
  cuenta sin verificar puede ser reemplazada por un registro nuevo con su usuario o su mail **solo después de que venció
  su link** (24 h).
- **Alternativas:** guardar los registros pendientes en otra tabla (más código, y el usuario no quedaría reservado);
  dejar que cualquiera reemplace una cuenta sin verificar en cualquier momento (cualquiera podría robar un registro en
  curso).
- **Consecuencias:** no hace falta un job de limpieza para que los nombres de usuario se liberen (pero ver 13).

### 3.3 Respuestas neutras, para que nadie pueda saber qué mails tienen cuenta

- **Decisión:** registrarse con un mail que ya tiene cuenta recibe la misma respuesta que un mail nuevo; el dueño de esa
  casilla recibe en cambio un mail de "ya tenés una cuenta". El nombre de usuario, en cambio, responde 409 explícito,
  porque la gente necesita elegir otro. La contraseña se hashea en todos los casos para que los tiempos de respuesta no
  delaten nada, y los mails se envían después de responder.
- **Consecuencias:** un poco más de maquinaria (una fila de log de mail sin token) para cuidar la privacidad de la gente.

### 3.4 Tokens de un solo uso, guardados hasheados, después del `#`

- **Decisión:** tokens de 256 bits, de los que solo se guarda el SHA-256, de un uso cada uno. El link es
  `/verify#token=...`; la página lee el fragmento y lo envía con un POST.
- **Por qué:** el fragmento nunca llega al servidor, así que los tokens nunca quedan en los logs de nginx ni en el
  `Referer`. Una página estática que hace POST (en vez de un link que actúa con GET) evita que los escáneres de mail
  gasten el token al abrir el link.

### 3.5 Topes de envío por cuenta y del sitio entero, enviados desde un pool de threads chico

- **Decisión:** topes por dirección (por hora, intervalo mínimo) y topes globales por hora y por día (el diario frena
  todo; el horario todavía deja salir la recuperación de contraseña). Los mails salen de un pool propio de 2 threads con
  una cola acotada.
- **Por qué:** un script que registra muchas direcciones distintas quemaría la reputación del remitente y la cuota del
  proveedor. Un servidor SMTP lento no tiene que retener los threads que sirven el mapa.

### 3.6 Sin CAPTCHA (por ahora)

- **Por qué:** los límites por IP, los topes por cuenta, las respuestas neutras y la verificación por mail alcanzaban
  para empezar. Se puede agregar después sin cambiar lo demás.

### 3.7 Diseño de los mails: logo adjunto, sin token visible, "no responder"

- **Decisión:** el link solo vive dentro del botón (el HTML nunca imprime la URL); el logo viaja dentro del mail; el
  remitente es "WebMet25 (no responder)" sin `Reply-To`, y se suprimen las respuestas automáticas.
- **Por qué:** los clientes de mail bloquean las imágenes remotas; un token visible invita a errores al copiar y pegar;
  las respuestas a una dirección que no se lee se perderían.

---

## 4. Ingreso con Google

- **Decisión:** el navegador muestra el botón de Google; la API verifica el ID token firmado contra las claves públicas
  de Google. La cuenta se busca primero por el id fijo de Google (`sub`) y después por mail. Google tiene que haber
  verificado el mail. Si no hay cuenta, se crea un viewer con el mail ya verificado. **Los admins generales nunca pueden
  entrar con Google.** Vincular una cuenta que nunca se verificó le borra la contraseña y le cierra las sesiones.
- **Alternativas:** buscar cuentas solo por mail (alguien que cambia su mail de Google perdería el acceso); permitir a
  los admins (una cuenta de Google comprometida se volvería un admin completo).
- **Consecuencias:** quien puso una contraseña en una cuenta sin verificar no es el dueño de la casilla; el usuario de
  Google sí, así que esa contraseña se descarta. Cuando un admin cambia el mail de una cuenta, se borra su vínculo con
  Google (el `sub` era del mail viejo), y la persona vuelve a vincularla en su próximo ingreso con Google.

---

## 5. Roles y permisos

### 5.1 Tres roles, y los permisos como concesiones aparte

- **Contexto:** la institución quería decidir, persona por persona, qué vistas de detalle de radar puede abrir cada uno,
  y más adelante repartir otras funciones.
- **Decisión:** el rol dice **qué tipo de usuario** es alguien (`admin`, `org_admin`, `viewer`); lo que puede abrir vive
  en una tabla `permissions`: **quién** (un usuario o una institución) + **acción** + **recurso**.
- **Alternativas:** un rol por combinación ("viewer con RMA1 y RMA17"), que explota; una tabla clásica de
  rol/permiso, que no puede expresar "este admin de institución recorta la lista de esta persona".
- **Consecuencias:** una función nueva es un texto de acción nuevo, no tablas nuevas (ver el registro de herramientas en
  10). El recurso es texto, así que no hay clave foránea al radar: el endpoint de admin borra los permisos de un radar
  en la misma transacción que el radar.

### 5.2 Un permiso abre la vista de detalle, no los datos

- **Decisión:** el permiso decide quién puede abrir `radar.html`. Los endpoints de datos son los mismos para todos los
  que tienen sesión, y todos siguen viendo todos los radares en el mapa principal.
- **Por qué:** la vista de detalle usa los mismos endpoints que el mapa. Esconder datos por usuario habría tocado todos
  los routers y el caché compartido de frames, para datos que la gente ya ve en el mapa.

### 5.3 El flag `detail_view_enabled` del radar significa "la vista está lista"

- **Decisión:** abrir una vista necesita el flag **y** el permiso; el admin general solo necesita el flag.
- **Por qué:** "la vista está configurada" y "quién la puede ver" son cosas distintas. Apagar el flag (mantenimiento)
  esconde la vista para todos sin tocar la lista de nadie.

### 5.4 "Todos" es un comodín que incluye los radares futuros

- **Decisión:** `*` como recurso.
- **Por qué:** quien recibe "todos" espera ver también los radares nuevos; asignar radar por radar se olvidaría.

### 5.5 Los permisos se leen de la base, no viajan en el JWT

- **Contexto:** se pensó en ponerlos en el token para ahorrar consultas.
- **Decisión:** se leen cuando una página pide `/permissions/me` (una vez por carga de página), no en cada pedido.
- **Por qué:** solo hacen falta al abrir la vista, así que el ahorro es chico; las herramientas y futuras listas por
  función agrandarían la cookie; y un cambio necesitaría que el token venza (o subir `token_version`) para verse.

### 5.6 Las cuentas nuevas arrancan sin vistas

- **Decisión:** el registro propio, el registro con Google y las cuentas que ya existían al momento de la migración
  arrancaron sin vistas; las asigna un admin.
- **Por qué:** un permiso es siempre una concesión explícita. El costo: después de ese deploy solo el admin podía abrir
  vistas de detalle hasta que se asignaron.

---

## 6. Instituciones (cuentas de empresa)

### 6.1 Instituciones con límite de lugares y permisos propios

- **Decisión:** una institución (por ejemplo una empresa de servicios) tiene un **límite de lugares** (usuarios activos,
  admins incluidos), sus propias vistas y herramientas, y uno o más **admins de institución** que manejan a sus miembros
  desde un panel limitado (`/empresa`). En pantalla se llama "institución"; en el código y la base sigue siendo
  `organization` / `org_admin`.
- **Por qué un panel aparte:** nginx protege `/admin` para el rol de admin general; esconder secciones con JavaScript
  no protegería nada.

### 6.2 Lo que ve un miembro = su lista ∩ la lista de la institución, calculado al leer

- **Decisión:** las vistas (y herramientas) efectivas de un miembro son la intersección de sus concesiones con las de
  la institución. Un admin de institución ve la lista de la institución.
- **Por qué:** si la institución pierde un radar, todos sus miembros lo pierden en el acto, sin tocar sus filas. Un
  miembro nuevo arranca con una **copia** de la lista de la institución, y el admin de institución la puede recortar por
  persona, nunca ampliar.

### 6.3 Lugares

- **Decisión:** desactivar libera un lugar; reactivar ocupa uno; bajar el límite por debajo de los usuarios activos no
  desactiva a nadie (solo bloquea los nuevos). Los lugares se chequean con la fila de la institución bloqueada.
- **Por qué:** sin la regla de reactivación, el límite se podría saltear desactivando y reactivando; sin el bloqueo,
  dos altas simultáneas podrían ocupar las dos el último lugar.

### 6.4 Una institución con usuarios activos siempre tiene un admin activo

- **Decisión:** la API rechaza (409) degradar, desactivar, desvincular o borrar al único admin activo mientras queden
  otros usuarios activos, y rechaza agregar un viewer a una institución sin admin activo.
- **Por qué:** los miembros de una institución sin admin no tendrían quién los maneje. Una institución sin usuarios
  puede no tener admin.

### 6.5 Los admins de institución desvinculan; solo el admin general mueve cuentas

- **Decisión:** el admin de institución "desvincula" a un viewer (la cuenta queda, como viewer sin institución y sin
  vistas) en vez de desactivarlo. Mover una cuenta entre instituciones, o sumar una cuenta existente, lo hace el admin
  general. Entrar a una institución reemplaza las vistas y herramientas de la cuenta por una copia de las de la
  institución; salir las saca; las dos cosas cierran las sesiones de la cuenta.
- **Por qué:** un admin de institución no tiene que poder dejar a alguien afuera de todo el sitio, ni llevarse cuentas
  de otra institución.
- **Cambió:** al principio la institución de una cuenta quedaba fija al crearla; después se permitió que el admin
  general mueva cuentas.

### 6.6 Crear una institución es todo o nada

- **Decisión:** nombre, lugares, su admin (nuevo, un viewer existente, una invitación o ninguno) y sus vistas y
  herramientas se crean en un solo pedido, dentro de una sola transacción.
- **Por qué:** una institución creada a medias (por ejemplo creada pero con el admin fallido) era confusa de arreglar a
  mano.

---

## 7. Invitaciones

- **Decisión:** un admin puede invitar a una persona por mail en vez de crearle la cuenta con contraseña. El admin
  general invita admins de institución o viewers a cualquier institución; un admin de institución invita viewers a la
  suya, dentro de sus propias vistas y herramientas. El link (`/invitacion#token=...`) dura 7 días y es de un solo uso.
  Una **invitación pendiente reserva un lugar**. Un ingreso con Google tiene que usar el mail invitado.
- **Invitar a alguien que ya tiene cuenta:** se puede. La página de la invitación le pregunta al servidor si el mail
  tiene cuenta **cuando se abre el link** (no se guarda nada) y muestra un login en vez del formulario de registro. Para
  unirse hacen falta **las dos cosas**, el link y una sesión de la cuenta de ese mail, así que el link solo no permite
  entrar a la cuenta de nadie. Solo el admin general puede invitar a un viewer de otra institución (aceptar lo mueve).
- **Por qué no decirle simplemente al que invita "ese mail tiene cuenta":** el que invita ya es admin, así que no sería
  una filtración, pero obligarlo a pasar por el admin general cada vez era demasiada fricción para un caso común.
- **Consecuencias:** las filas de invitaciones nunca se borran (las aceptadas, canceladas y vencidas quedan como
  registro) y cuentan para los topes de envío de mails.

---

## 8. Borrar usuarios e instituciones

### 8.1 Borrar usuarios es real, después de una etapa de "solo desactivar"

- **Cambió:** al principio los usuarios nunca se borraban, solo se desactivaban, para conservar la identidad para una
  auditoría futura. Se cambió a un borrado real: el admin general borra a otros, y cada persona puede borrar su propia
  cuenta.
- **Reglas:** un admin general no puede borrar su propia cuenta (lo hace otro admin general), y no se puede borrar al
  último admin general activo; aplica la regla de la institución (6.4). La confirmación es un diálogo manual, sin
  contraseña.
- **Riesgo aceptado:** alguien con una sesión abierta en una computadora compartida podría borrar esa cuenta. Solo afecta
  a la propia cuenta, y los admins generales no se pueden borrar a sí mismos. Pedir la contraseña se puede agregar sin
  cambiar lo demás.
- **Consecuencias:** los campos de "quién otorgó esto" o "quién invitó" en otras filas quedan vacíos; el vínculo con
  Google se va con la cuenta, así que el mail se puede volver a invitar.

### 8.2 Borrar una institución obliga a decidir qué pasa con sus usuarios

- **Decisión:** una institución con usuarios (activos o no) no se borra hasta que el admin general elige
  **desvincularlos** (por defecto) o **borrarlos** también; borrarlos exige escribir el nombre de la institución. Todo
  corre en una sola transacción. Las invitaciones pendientes, y el historial de las aceptadas y canceladas, se van con
  ella.
- **Por qué:** borrar cuentas de personas como efecto secundario de borrar una empresa tiene que ser un acto
  deliberado.

---

## 9. Perfil y textos de los mails

### 9.1 Una sola página de perfil; solo se edita el nombre

- **Decisión:** `/perfil` para todos los roles (dentro del panel para los admins). Usuario y mail son de solo lectura
  ahí.
- **Por qué:** cambiar el mail implica verificarlo de nuevo, y cambiar el usuario rompe cómo se conoce la gente; las dos
  cosas quedan para los admins. Se diseñó una foto de perfil pero quedó afuera (sin subida de archivos, sin volumen).

### 9.2 Textos de los mails editables desde el panel, diseño fijo en el código

- **Decisión:** el admin general puede editar el texto de los cuatro mails (asunto, título, párrafos, texto del botón,
  pie). El logo, el diseño, el botón y su link, y el aviso de "no responder" quedan en el código. Solo existe una fila
  cuando un mail se personalizó; si no, se usa el texto del código. Los marcadores (`{usuario}`, ...) se validan al
  guardar.
- **Por qué:** cambiar una redacción no tiene que necesitar un deploy, pero el link con el token y el diseño no se
  tienen que poder romper desde el panel. Sin fila, un deploy nunca cambia un mail por sorpresa. El texto es plano
  (cualquier HTML se muestra como texto).

---

## 10. Herramienta de seguimiento de tormentas

### 10.1 Una herramienta de sí o no, no una lista de radares

- **Decisión:** el seguimiento de tormentas es una **herramienta** (`tool.tracking`, recurso `*`) que un usuario o una
  institución tiene o no. Aparece en todas las vistas de radar que la persona puede abrir.
- **Alternativas:** un permiso de seguimiento por radar (una segunda lista que duplica las vistas).
- **Consecuencias:** sacarle a alguien la vista de un radar también le saca su seguimiento; no hay otra lista que
  mantener sincronizada.
- **Cambió:** la sección "Vistas" del panel pasó a llamarse "Herramientas" e incluye las vistas y esta herramienta.

### 10.2 Las mismas reglas que las vistas, más "encenderla llega a todos"

- **Decisión:** miembro = su concesión ∩ la de la institución; el admin de institución solo la puede dar si la
  institución la tiene; las invitaciones llevan la elección. Cuando el admin general enciende la herramienta para una
  institución, **todos los miembros actuales la reciben**; el admin de institución se la saca a quien no deba tenerla.
- **Por qué:** encender una herramienta para una institución y después tener que tildar a cada miembro a mano era la
  queja común. El panel avisa cuando una concesión no tiene efecto (por ejemplo un miembro de una institución sin la
  herramienta).

### 10.3 La aplica nginx, y por radar en las rutas por radar

- **Decisión:** el servicio de seguimiento no sabe de sesiones; nginx es su única puerta. Todas las rutas
  `/api/tracking/` y la página `/tracking` necesitan la herramienta; las rutas que llevan el radar en la URL
  (`/api/tracking/radars/<código>/...`) necesitan la herramienta **y** la vista de ese radar.
- **Por qué:** un trabajo de seguimiento cuesta segundos de CPU, así que esconder el botón no alcanza. El radar se puso
  en la URL de las rutas nuevas justamente para que nginx lo pueda chequear sin leer el cuerpo.
- **Consecuencias:** las rutas viejas (`POST /api/tracking/jobs`, `/api/tracking/availability`), que solo usa la página
  de prueba `tracking.html`, solo chequean la herramienta. Los límites de uso (por usuario o por IP) quedaron para
  después; el servicio corre un trabajo a la vez y comparte los pedidos idénticos.

### 10.4 Agregar una herramienta es una lista de pasos

- **Decisión:** las herramientas están en un solo registro (`TOOLS` en la API, `TOOL_LIST` en el frontend); un test
  falla y dice qué paso se olvidó. Ver [`OPERATIONS.md`](OPERATIONS.md), "How to add a tool".

---

## 11. Infraestructura y rendimiento

### 11.1 Pool de la base dimensionado para que todos los workers entren en PostgreSQL

- **Contexto:** cada worker de Uvicorn tiene su propio pool; 4 workers × (10 + 20) = 120 conexiones posibles contra
  las 100 de PostgreSQL. Ante una ráfaga, las conexiones de más se rechazaban y los pedidos fallaban.
- **Decisión:** `DB_MAX_OVERFLOW=12` para la API (4 × 22 = 88), pasado desde el compose para que cada servidor lo
  ajuste según la cantidad de workers.
- **Alternativas:** subir `max_connections` (más memoria, y más consultas simultáneas no son más rápidas en los mismos
  núcleos); PgBouncer (la respuesta correcta a mayor escala, todavía no hace falta).
- **Consecuencias:** los pedidos de más esperan unos milisegundos en el pool en vez de fallar. Subir
  `UVICORN_WORKERS` obliga a rehacer la cuenta.

### 11.2 Los tiles del mapa base chequean solo el JWT, sin leer la base

- **Contexto:** mover el mapa pide decenas de tiles del mapa base a la vez, y cada uno pasaba por el chequeo completo de
  sesión (1.2), usando una conexión a la base por tile.
- **Decisión:** los proxies de tiles le preguntan a un chequeo más liviano (`/api/v1/auth/check-token`) que solo
  verifica el access token firmado, `async` y sin sesión de base.
- **Consecuencias:** una excepción a 1.2: un usuario desactivado sigue recibiendo tiles del mapa base (imágenes públicas
  de OSM/IGN) hasta que vence su access token (30 minutos como máximo). Todo lo demás se corta en el acto.

### 11.3 IP real del cliente detrás de los proxies

- **Contexto:** en stage la cadena es Tailscale Funnel → Caddy → nginx. nginx veía al gateway de Docker como cliente de
  todos los pedidos, así que los límites por IP eran un solo contador para todo internet.
- **Decisión:** nginx confía en `X-Forwarded-For` solo si viene de las redes de Docker y de localhost
  (`set_real_ip_from`, `real_ip_recursive on`) y lo lee desde la derecha; Caddy confía en el proxy local
  (`trusted_proxies`). nginx se publica en `127.0.0.1` por defecto (`FRONTEND_BIND`).
- **Por qué desde la derecha:** lo que un cliente escriba en ese header queda a la izquierda, así que no puede falsear
  su dirección.

### 11.4 Base path: la misma imagen se puede servir bajo un prefijo

- **Contexto:** dos copias del sitio tenían que compartir un mismo hostname (`/` y `/nacho/`).
- **Decisión:** el proxy saca el prefijo y lo avisa en `X-Forwarded-Prefix`; nginx lo valida (un solo segmento simple)
  y lo escribe en el `<base href>` de cada página; las URLs de la app son siempre relativas; los nombres de las cookies y
  el path del refresh llevan el prefijo.
- **Alternativas:** una variable `BASE_PATH` fija (la misma copia no andaría con y sin prefijo); reescribir cada
  `location` de nginx (invasivo).
- **Consecuencias:** una regla del equipo: **las URLs de la app nunca empiezan con `/`** (ver
  [`COMPONENTS.md`](COMPONENTS.md), "Base path"). `tests/e2e/test_base_path.py` recorre todas las páginas detrás de un
  proxy de prueba y falla si algo se sale del prefijo. `history.replaceState` con un `#` tiene que usar el path
  completo, o se resuelve contra el `<base>`.

---

## 12. Tests

### 12.1 Los tests de caja negra corren contra un stack aislado

- **Contexto:** las suites de API y e2e crean usuarios y sesiones; corrían contra la base de desarrollo.
- **Decisión:** `tests/api` y `tests/e2e` corren contra su propia API, frontend y base (`api-e2e`, `frontend-e2e`,
  `radar_e2e_db`), en una red de Docker privada, usando otro índice de Redis.
- **Consecuencias:** las suites nunca escriben en los datos reales. Los caminos felices que escriben se prueban en
  proceso en `tests/auth`, contra la base de test; `tests/api` solo prueba los caminos de error de los endpoints que
  escriben.

### 12.2 Las reglas de concurrencia tienen sus propios tests

- **Decisión:** los bloqueos (rotación del refresh, último lugar de una institución) se prueban con dos conexiones
  reales y una pausa forzada, porque un test normal pasaría aunque no estuviera el bloqueo.

---

## 13. Interfaz

### 13.1 Un tooltip propio, una burbuja flotante

- **Contexto:** el navegador dibuja un `title` como una caja con borde oscuro que no se puede estilar, y un tooltip hecho
  en CSS dentro de una tabla quedaba tapado por el encabezado fijo (y cortado por la caja con scroll de la tabla).
- **Decisión:** una sola burbuja, hija de `<body>` con `position: fixed`, alimentada por todos los `title` de la página
  (también los que el código pone después) y por el `<title>` dentro de los íconos. Se abre arriba de su control y pasa
  abajo si no hay lugar.
- **Alternativas:** un `::after` en cada control (lo cortan el `overflow` y los contextos de apilamiento; falló en las
  tablas); dejar el del navegador (sin control del aspecto ni de los tiempos).
- **Consecuencias:** el texto pasa de `title` a `data-tooltip` y a `aria-label`; los campos de texto se saltean porque su
  `title` también es parte del mensaje de formato del navegador. Una página con tooltips carga un script.

### 13.2 Una ventana de confirmación propia en lugar de `window.confirm`

- **Decisión:** `confirmAction` es una ventana chica con el movimiento de las demás, que responde con una promesa. En una
  acción que no se puede deshacer, el botón rojo la hace y el foco arranca en Cancelar.
- **Por qué:** el cuadro del navegador no se puede estilar ni animar y se ve distinto en cada sistema. El costo es que
  cada pregunta pasó a ser asincrónica, y los tests e2e responden la ventana (`answer_confirmation`) en lugar del
  diálogo del navegador.

### 13.3 Un solo chip de cuenta para el mapa y los paneles, en dos temas

- **Decisión:** la misma píldora (avatar, nombre, rol, salir) en todos lados; cada color es una variable. El mapa
  conserva el tema oscuro; los paneles usan uno claro, porque una píldora oscura resaltaba demasiado en un encabezado
  claro. En el tema claro la insignia del administrador general es azul (el color del panel) y la del admin de
  institución es gris pizarra.
- **Alternativas:** un chip distinto en cada lugar (se desalineaban); la píldora oscura en los paneles (muy llamativa);
  una insignia amarilla para el administrador general (no combinaba con los paneles azules).
- **Consecuencias:** el atajo al panel del rol existe solo en el mapa; un panel tiene solo el botón de salir, porque la
  persona ya está ahí.

### 13.4 Acciones de la fila como íconos; las poco frecuentes viven en "Seguridad"

- **Contexto:** la tabla de usuarios tenía demasiados botones por fila.
- **Decisión:** íconos con tooltip para las frecuentes (editar, herramientas, eliminar); **Seguridad** (un candado) abre
  una ventana con resetear contraseña, cerrar sesiones y desactivar o activar. Eliminar es su propio basurero, al final
  y blanco (un relleno rojo llamaba demasiado la atención).
- **Alternativas:** botones de texto más chicos (solo posterga el problema), mover las poco frecuentes al formulario de
  edición.

### 13.5 Menú lateral plegable; el grupo activo siempre abierto

- **Decisión:** los grupos se abren y se cierran con una animación suave. El grupo que tiene el enlace activo siempre
  está abierto. En el panel de admin los demás arrancan cerrados, porque su menú es largo; los paneles de institución y
  de perfil tienen un par de enlaces, así que todo arranca abierto. Lo que la persona abre se recuerda, para cada panel
  por separado.
- **Descartado:** un barrido de radar animado como fondo del sidebar. Se probó (anillos y un haz, solo CSS) y se sacó: se
  veía solo abajo y no convencía. El panel del login conserva su radar y toma el color del sidebar.

### 13.6 "Mis datos" como una tarjeta compacta

- **Decisión:** el encabezado (avatar, nombre, `@usuario`, rol, "Editar nombre") y, bajo una línea, los datos que no están
  ya en el encabezado. Dos tarjetas grandes repetían el usuario, el nombre y el rol.

### 13.7 Movimiento: corto, suave y fácil de apagar

- **Decisión:** ventanas, avisos, secciones, filas de tabla y listas de búsqueda se animan brevemente, solo con
  transformación y opacidad (el navegador lo hace en la placa gráfica). Al cerrar una ventana primero se desvanece y
  recién después se vacía su formulario. Una sección se anima cuando cambia, no cuando se dibuja la misma después de
  una acción (parpadearía).
- **Por qué:** ayuda al ojo a seguir lo que cambió; nunca debe demorar lo que la persona quiere hacer, así que todo se
  apaga con `prefers-reduced-motion`.
- **Queda para después:** los paneles flotantes del mapa se abren con una animación pero todavía se cierran de golpe.

---

## 14. Pendientes conocidos

Quedaron afuera a propósito y conviene conocerlos:

- No hay job de limpieza para cuentas sin verificar y tokens de mail vencidos; los logs de nginx no rotan.
- Las cuentas creadas por un admin nunca ven la casilla de términos.
- No hay CAPTCHA, ni límites de uso para el servicio de seguimiento.
- Aceptar una invitación cuyo radar se borró mientras tanto falla (la invitación conserva el código).
- Los textos legales (términos y privacidad) todavía no están escritos; el registro no los puede exigir hasta que
  existan.
