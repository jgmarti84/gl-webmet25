# Manual de usuario — WebMet25

WebMet25 es el visor de radares meteorológicos del **Observatorio Hidro-Meteorológico de Córdoba (OHMC)**: muestra en
un mapa, casi en tiempo real, los datos de la red de radares, con animación, una vista de detalle por radar y una
herramienta de seguimiento de tormentas.

Este manual explica **qué puede hacer cada tipo de usuario** y cómo. Está pensado para quienes usan el sitio, no para
quienes lo programan (para eso están los demás documentos de `docs/`).

**Contenido**

1. [Los tres roles](#1-los-tres-roles)
2. [Para todos: entrar y usar la cuenta](#2-para-todos-entrar-y-usar-la-cuenta)
3. [El mapa](#3-el-mapa)
4. [La vista de un radar](#4-la-vista-de-un-radar)
5. [Seguimiento de tormentas](#5-seguimiento-de-tormentas)
6. [Mi perfil](#6-mi-perfil)
7. [Admin de institución: el panel de su institución](#7-admin-de-institución-el-panel-de-su-institución)
8. [Administrador general: el panel de administración](#8-administrador-general-el-panel-de-administración)
9. [Reglas que conviene conocer](#9-reglas-que-conviene-conocer)
10. [Problemas frecuentes](#10-problemas-frecuentes)

---

## 1. Los tres roles

Para usar el sitio hace falta una cuenta: **sin iniciar sesión no se ve nada**. Cada cuenta tiene uno de estos roles:

| Rol | En pantalla | Quién es |
|---|---|---|
| **Lector** | "Lector" | La mayoría de los usuarios. Mira el mapa y las vistas de radar que tenga habilitadas |
| **Admin de institución** | "Admin de institución" | Administra a las personas de **su** institución (por ejemplo, una empresa o un organismo) |
| **Administrador general** | "Administrador" | Administra todo el sitio: usuarios, instituciones, radares y configuración |

Una **institución** es un grupo de usuarios (por ejemplo, EPEC) con un **tope de lugares** (cuántas cuentas activas
puede tener) y sus propias **herramientas**: qué vistas de radar y qué herramientas (como el seguimiento de tormentas)
pueden usar sus miembros. Un lector puede pertenecer a una institución o no.

**Qué puede hacer cada uno, de un vistazo:**

| | Lector | Admin de institución | Administrador general |
|---|:---:|:---:|:---:|
| Ver el mapa con todos los radares | ✅ | ✅ | ✅ |
| Abrir la vista de un radar | Las que tenga habilitadas | Las de su institución | Todas |
| Usar el seguimiento de tormentas | Si tiene la herramienta | Si su institución la tiene | ✅ |
| Ver su perfil, cambiar su nombre, borrar su cuenta | ✅ | ✅ (con condiciones, ver §9) | Ver su perfil y su nombre; no puede borrarse a sí mismo |
| Crear e invitar usuarios | — | En su institución | En cualquier institución |
| Asignar vistas y herramientas | — | A los lectores de su institución, dentro de lo que tiene la institución | A cualquiera |
| Crear, editar y borrar instituciones | — | — | ✅ |
| Administrar radares, productos, mapas de colores, textos de los mails | — | — | ✅ |

---

## 2. Para todos: entrar y usar la cuenta

### 2.1 Iniciar sesión

En la página de inicio de sesión se entra con el **usuario o el mail**, más la contraseña.

- **Continuar con Google:** si aparece el botón, se puede entrar con una cuenta de Google que tenga el mismo mail que
  la cuenta de WebMet25. El administrador general no puede usar esta opción.
- **Si te equivocás 5 veces seguidas** con la contraseña, la cuenta queda bloqueada **15 minutos**. Después se puede
  volver a intentar, o pedirle a un administrador que te ponga una contraseña nueva.
- **Si entrás a una página directamente** (por ejemplo, un link al panel), el sitio te pide iniciar sesión ahí mismo y,
  al entrar, te deja en esa página.

### 2.2 La sesión

- La sesión **se renueva sola** mientras el sitio esté abierto: no hace falta volver a entrar cada media hora.
- Se cierra sola después de **48 horas sin usarla**, y como máximo a los **7 días** de haber entrado.
- **Cerrar sesión:** en el mapa, desde la franja de tu cuenta, arriba a la derecha (tu nombre e iniciales).
- Si un administrador te cambia el rol, la institución o la contraseña, o cierra tus sesiones, tenés que volver a
  entrar.

### 2.3 Contraseñas

- Mínimo **10 caracteres**, con **al menos un carácter especial** (por ejemplo `! - _ . @ #`).
- **Olvidé mi contraseña:** desde el inicio de sesión, "¿Olvidaste tu contraseña?". Llega un mail con un botón que vale
  **1 hora** y sirve una sola vez. La contraseña nueva tiene que ser distinta de la actual.
- Los mails del sitio llegan de **"WebMet25 (no responder)"**: no los respondas. Para ayuda, escribí a
  **info@ohmc.ar**.

### 2.4 Crear una cuenta (si el registro está habilitado)

Si en el inicio de sesión aparece **"Crear cuenta"**, se puede registrar uno mismo: usuario, nombre (opcional), mail y
contraseña. Llega un mail para **confirmar el mail** (el botón vale 24 horas); hasta confirmarlo no se puede entrar.

Una cuenta nueva **no tiene vistas de radar ni herramientas**: se las asigna un administrador.

### 2.5 Aceptar una invitación

Un administrador puede invitarte por mail a una institución. El mail trae un botón que **vale 7 días** y sirve una
sola vez:

- **Si no tenés cuenta:** completás tu usuario, nombre y contraseña, o usás **Google** con la cuenta de ese mismo mail.
  Entrás directamente, ya dentro de la institución.
- **Si ya tenés cuenta con ese mail:** la página te pide **iniciar sesión** con esa cuenta, y al entrar te sumás a la
  institución. Si estabas en otra institución, salís de ella y recibís las vistas y herramientas de la invitación.

Si el link venció o ya se usó, pedile a quien te invitó que te lo reenvíe.

---

## 3. El mapa

Es la página principal. **Todos los usuarios ven todos los radares** en el mapa.

- **Radares:** la lista de la red, con su estado (activo o inactivo). Se elige cuáles mostrar.
- **Modo:** **C+D** (convencional y Doppler) o **Vigilancia** (largo alcance).
- **Campo:** la variable que se ve (por ejemplo, reflectividad), con su leyenda de colores. Algunos campos tienen una
  versión **filtrada**.
- **Ventana de tiempo y animación:** cuánto tiempo hacia atrás se anima, con controles de reproducir y pausar.
- **Modo en vivo:** el mapa se actualiza solo con los datos nuevos (por defecto, cada 5 minutos).
- **Ajustes:** el mapa de fondo, la cobertura de los radares, el suavizado, y los **Tops & Cores** (núcleos y topes de
  tormenta, disponibles con el campo COLMAX).
- **Botón ›** junto a un radar: abre su **vista de radar** (§4). Solo aparece en los radares que podés abrir.
- **Franja de cuenta**, arriba a la derecha: tu nombre, el acceso a **Mi perfil** (lectores), al **Panel de
  institución** (admins de institución) o al **Panel de administración** (administrador general), y **cerrar sesión**.

Los datos son productos automáticos de la red de radares: pueden tener errores o demoras y **no reemplazan los avisos
oficiales**.

---

## 4. La vista de un radar

Es una página dedicada a un solo radar, con más detalle. Se abre con el botón **›** junto al radar en el mapa.

- **Quién la puede abrir:** el administrador general, todas; el resto, **solo las que le asignaron** (§8.2 y §7.3).
  Los miembros de una institución, además, solo las que tenga su institución.
- Si alguien abre la dirección de un radar que no tiene asignado, ve **"No tenés acceso a la vista de este radar"** y
  vuelve al mapa en 5 segundos.
- Si un administrador apaga la vista de un radar (por mantenimiento), no la ve nadie hasta que la vuelva a encender.

---

## 5. Seguimiento de tormentas

Es una **herramienta** dentro de la vista de un radar: sigue las tormentas a lo largo de los últimos barridos del
radar, dibuja por dónde se movieron y estima hacia dónde van.

### 5.1 Quién la tiene

- El **administrador general**, siempre.
- Un **admin de institución**, si su institución la tiene.
- Un **lector**, si se la dieron **y** (si está en una institución) su institución la tiene.

Se usa en **cada vista de radar que la persona puede abrir**. Si no tenés la herramienta, el botón no aparece. Si no
hay datos de seguimiento para un radar, tampoco.

### 5.2 Cómo se usa

En la vista de un radar, el botón **⛈ Seguimiento de tormentas** abre su panel:

- **Mostrar seguimiento:** prende o apaga la herramienta. Mientras está apagada no calcula nada.
- **Últimos volúmenes de la ventana:** cuántos barridos seguir (**3, 5 o 10**). Se dibujan sobre los últimos cuadros de
  la animación.
- **Pronósticos:** a cuántos minutos hacia adelante estimar la posición de cada tormenta (por ejemplo 18, 36 y 54).
- **Trayectorias:** muestra el recorrido de cada tormenta.
- **Parámetros del seguimiento:** CAPPI (altura sobre la antena), umbral de detección (dBZ), área mínima (km²) y
  crecimiento en pronósticos. Después de cambiarlos, **Recalcular seguimiento**; **Restablecer** vuelve a los valores
  por defecto. **Configuración en uso** muestra los valores con que se calculó lo que estás viendo.
- El cálculo tarda unos segundos (dice "Calculando seguimiento…"). Si varias personas miran lo mismo, se calcula una
  sola vez.
- Las elecciones (cantidad de volúmenes, pronósticos, trayectorias, parámetros) se recuerdan en tu navegador.

---

## 6. Mi perfil

Muestra tus datos: usuario, nombre, mail, rol, institución, fecha de alta y último ingreso, y **los radares cuya vista
podés abrir**. Un admin de institución ve además la tarjeta de **su institución** (lugares y lo que tiene habilitado).

- **Cómo llegar:** los lectores, desde la franja de cuenta del mapa. Los admins, desde **"Mi perfil"** en el menú de su
  panel.
- **Qué se puede cambiar:** solo el **nombre**. El usuario y el mail los cambia un administrador.
- **Eliminar mi cuenta:** al pie del perfil. Pide una confirmación y **no se puede deshacer**: se borran la cuenta y sus
  sesiones. Hay excepciones en §9.

---

## 7. Admin de institución: el panel de su institución

Se abre desde la franja de cuenta del mapa, con el botón **"Panel de institución"**. Arriba muestra el nombre de la
institución, los **lugares** usados ("3 de 5") y lo que la institución tiene habilitado.

### 7.1 Agregar usuarios

**"Agregar usuario"** ofrece dos formas. En las dos, la persona entra como **lector de tu institución**, y se marcan
las **vistas de radar** y las **herramientas** con las que empieza (solo se ofrece lo que tiene la institución, y
viene todo marcado):

- **Crear con una contraseña inicial:** usuario, nombre, mail y contraseña inicial (pasásela a la persona por un
  medio seguro).
- **Invitar por mail:** la persona recibe un link para crear su cuenta o, si ya tiene una, para sumarse con ella (§2.5).

Las dos necesitan un **lugar libre**. Una **invitación pendiente reserva un lugar** hasta que se acepta, se cancela o
vence. Las pendientes aparecen en su lista con **Reenviar** (manda un link nuevo; el anterior deja de servir) y
**Cancelar**.

Si el usuario o el mail ya existe en otra cuenta, el panel te avisa: para sumar a esa persona, pedíselo al
administrador general (o invitala por mail, si no está en otra institución).

### 7.2 Administrar a los usuarios

En la tabla de usuarios, cada lector tiene sus botones:

- **Editar:** nombre y mail.
- **Resetear contraseña:** le ponés una contraseña nueva; se le cierran las sesiones.
- **Cerrar sesiones:** lo obliga a volver a entrar.
- **Desvincular:** la persona deja tu institución. Libera su lugar, pierde las vistas y herramientas que le dio la
  institución y se le cierran las sesiones. **La cuenta sigue existiendo**; solo el administrador general puede
  volver a sumarla.
- **Herramientas:** sus vistas de radar y sus herramientas (§7.3).

Los demás admins de la institución aparecen en la lista, pero no los podés modificar: eso lo hace el administrador
general.

### 7.3 Herramientas (vistas de radar y seguimiento)

El botón **Herramientas** de cada lector abre una ventana con:

- **Vistas de radar:** qué radares puede abrir. Solo se ofrecen los que tiene la institución. Si la institución tiene
  "Todas", podés darle "Todas" o elegir radares.
- **Seguimiento de tormentas:** la casilla aparece solo si la institución tiene la herramienta.

Podés **achicar** lo que tiene cada uno, pero nunca darle algo que la institución no tiene. Cuando el administrador
general le da el seguimiento a la institución, **todos sus usuarios lo reciben en ese momento**; si alguno no tiene que
tenerlo, se lo sacás desde acá.

---

## 8. Administrador general: el panel de administración

Se abre desde la franja de cuenta del mapa. El menú lateral tiene estas secciones:

| Grupo | Secciones |
|---|---|
| **Cuenta** | Panel (resumen), Mi perfil |
| **Datos** | Radares, Productos, Referencias, COGs, Tops & Cores, Cubos NetCDF |
| **Configuración** | Estrategias, Volúmenes, Textos de los mails |
| **Mapas de colores** | Mapas de colores, Opciones de mapa de colores |
| **Acceso** | Usuarios, Instituciones, Invitaciones |

Las secciones de **Datos**, **Configuración** y **Mapas de colores** administran el contenido del visor (qué radares
existen, sus productos, sus escalas de colores). Entre ellas, en **Radares** se enciende o apaga la **vista de
detalle** de cada radar. Este manual se centra en la parte de **Acceso**.

### 8.1 Usuarios

- **Agregar usuario:** usuario, nombre, mail, rol y contraseña inicial. Se puede elegir una **institución**; para el
  rol "Admin de institución", la institución es obligatoria.
- **Editar:** nombre, mail, rol, activo o inactivo, e **institución** (para sumar un lector a una institución, moverlo
  a otra o sacarlo con "Ninguna"). El formulario avisa qué va a pasar antes de guardar: al entrar a una institución,
  la persona ocupa un lugar y sus vistas y herramientas pasan a ser **una copia de las de la institución**; al salir,
  las pierde. En los dos casos se le cierran las sesiones.
- **Herramientas:** vistas de radar ("Todas", incluidos los radares futuros, o radares sueltos) y seguimiento de
  tormentas. Si la persona es de una institución que **no** tiene algo, la ventana avisa que darlo **no tiene efecto**:
  cada miembro ve solo lo que tiene él **y** su institución.
- **Desactivar / activar:** desactivar impide entrar y libera el lugar en la institución; se puede revertir.
- **Seguridad:** **Resetear contraseña** (define una nueva y cierra sus sesiones; la propia se cambia desde el
  servidor) y **Cerrar sesiones** (lo obliga a volver a entrar en todos sus dispositivos).
- **Verificar mail:** para una cuenta registrada que nunca confirmó su mail.
- **Eliminar** (basurero en la fila): pide confirmación y **no se puede deshacer**.
- Las tablas muestran, para cada usuario, lo que tiene **él** y lo que tiene **su institución**.

### 8.2 Instituciones

- **Agregar institución:** nombre, **tope de lugares** (usuarios activos, admins incluidos), si está activa, y en el
  mismo formulario:
  - **Su admin:** crear uno nuevo, **elegir un lector que ya existe** (con un buscador por usuario, nombre o mail),
    **invitar por mail**, o dejarlo para después.
  - **Sus herramientas:** vistas de radar y seguimiento de tormentas.

  Todo se crea en un solo paso: si algo falla (un nombre repetido, una contraseña débil), no se crea nada.
- **Editar:** nombre, tope de lugares y si está activa. Una institución **desactivada** deja a todos sus usuarios sin
  poder entrar.
- **Herramientas:** lo que la institución puede repartir. **Quitarle algo se lo quita a todos sus miembros al
  instante.** **Darle el seguimiento de tormentas se lo da a todos sus usuarios** en ese momento.
- **Usuarios:** abre la sección Usuarios filtrada por esa institución. Desde la edición de la institución también se
  pueden **sumar personas** que ya tienen cuenta.
- **Eliminar institución** (botón de basurero):
  - Sin usuarios, pide una confirmación.
  - Con usuarios, ofrece **Desvincularlos** (opción por defecto: quedan como lectores sin institución, sin vistas ni
    herramientas, y sus admins pasan a lector) o **Eliminar también a sus usuarios** (se borran sus cuentas; hay que
    escribir el nombre de la institución para habilitar el botón).
  - Las invitaciones pendientes se cancelan. **No se puede deshacer.**
- Bajar el tope por debajo de los usuarios activos **no desactiva a nadie**: solo impide sumar gente nueva.

### 8.3 Invitaciones

Lista todas las invitaciones pendientes, con **Reenviar** y **Cancelar**. **"Invitar por mail"** permite invitar a un
admin de institución o a un lector, eligiendo la institución. Para un lector se elige además si tiene el seguimiento de
tormentas; sus vistas de radar son una copia de las de la institución (después se ajustan con **Herramientas**). Un
admin de institución usa lo que tiene su institución.

- Se puede invitar a alguien que **ya tiene cuenta**: el sitio avisa y la invitación sale igual (al aceptar, entra con
  su cuenta). Si es un lector de **otra** institución, al aceptar se mueve a la nueva.
- Un lector solo se puede invitar a una institución que ya tenga un **admin activo**.

### 8.4 Textos de los mails

Permite cambiar el **texto** de los cuatro mails del sitio (confirmar el mail, recuperar la contraseña, "ya tenés una
cuenta" y la invitación) sin tocar código: asunto, título, párrafos, texto del botón y pie.

- Se pueden usar **marcas** que se reemplazan al enviar (por ejemplo `{usuario}`, `{horas}`, `{institucion}`). La
  pantalla muestra cuáles acepta cada mail y tiene botones para insertarlas.
- La **vista previa** muestra el mail como va a llegar, mientras se escribe.
- **Restaurar original** vuelve al texto de fábrica.
- El logo, el diseño y el botón no se cambian desde acá.

---

## 9. Reglas que conviene conocer

- **Lugares:** cada institución tiene un tope de usuarios **activos** (admins incluidos). Las invitaciones pendientes
  también ocupan lugar. Desactivar o desvincular a alguien libera el suyo.
- **Toda institución con usuarios activos tiene que tener un admin activo.** Por eso el sitio no deja bajar a lector,
  desactivar, desvincular ni borrar al **único** admin activo mientras queden otros usuarios activos: primero hay que
  nombrar a otro.
- **Lo que ve un miembro = lo suyo y lo de su institución.** Si la institución pierde un radar o una herramienta, todos
  sus miembros la pierden al instante. Un admin de institución tiene lo de su institución.
- **Quien entra a una institución** (creado, invitado o movido) empieza con una copia de lo que tiene la institución.
  **Quien sale** pierde lo que le dio la institución.
- **Borrar es definitivo** (usuarios e instituciones). Desactivar, en cambio, se puede revertir.
- **Quién puede borrar qué:** cada persona puede borrar su propia cuenta, salvo el administrador general (lo hace otro
  administrador general) y el único admin activo de una institución con más usuarios activos. Solo el administrador
  general borra a otras personas.
- **El mapa es igual para todos:** las vistas de radar y las herramientas deciden qué páginas y funciones se abren, no
  qué radares se ven en el mapa principal.

---

## 10. Problemas frecuentes

| Problema | Qué hacer |
|---|---|
| "Usuario o contraseña incorrectos" | Revisá mayúsculas; se puede entrar con el usuario o con el mail. Si no recordás la contraseña, "¿Olvidaste tu contraseña?" |
| La cuenta quedó bloqueada | Esperá 15 minutos o pedile a un administrador que te ponga una contraseña nueva |
| "Tenés que verificar tu mail para entrar" | Abrí el mail de confirmación (revisá spam). El inicio de sesión ofrece reenviarlo |
| No veo el botón › de un radar | No tenés asignada esa vista. Pedísela al admin de tu institución o al administrador general |
| No veo el seguimiento de tormentas | No tenés la herramienta, o no hay datos de seguimiento para ese radar |
| El link de un mail no funciona | Venció o ya se usó. Pedí uno nuevo (recupero de contraseña, reenvío de confirmación o reenvío de la invitación) |
| "La institución no tiene lugares libres" | Hay que liberar un lugar (desactivar o desvincular a alguien, o cancelar una invitación) o pedir al administrador general que suba el tope |
| Me sacaron de golpe de la sesión | Un administrador cambió algo de tu cuenta (rol, institución, contraseña) o cerró tus sesiones. Volvé a entrar |
| Cualquier otra consulta | Escribí a **info@ohmc.ar** |
