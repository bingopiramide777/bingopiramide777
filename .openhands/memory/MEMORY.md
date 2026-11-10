# Proyecto: Bingo Pirámide 777

Bingo de 75 bolas ORIGINAL del usuario. Repo `bingopiramide777/bingopiramide777`,
rama `main`. **NO copiar** nada de Juegoactivo (ni diseño, ni textos, ni login Facebook).
Diseño: morado + dorado + verde, portada con el puente sobre el lago de Maracaibo.

## Cuenta de administración
`bingopiramide777@gmail.com`. Se crea al primer arranque con `BINGO_ADMIN_CLAVE`
(o aleatoria, se imprime una vez). Los jugadores se registran con su correo
(nunca como admin: `registrar()` fuerza rol `jugador`).

## Arquitectura
- `nucleo/almacen.py` — **SQLite**, un fichero (`BINGO_DB`, por defecto `bingo777.db`).
  Cada movimiento de dinero va en una transacción; `CHECK (centimos >= 0)` +
  `resolver_retiro` con `WHERE estado='pendiente'` dan idempotencia.
- `nucleo/monedero.py` — **solo céntimos int**. Conversión en el borde con `a_centimos`.
- `nucleo/usuarios.py` — PBKDF2 200k, roles `jugador`/`admin`, sesiones en la DB.
- `nucleo/retiros.py` — el dinero se descuenta **al pedir**; pagar NO mueve saldo,
  rechazar **devuelve**. Un retiro solo se resuelve una vez.
- `web/servidor.py` — `http.server` puro. Estado en `servidor.juego` (clase `Juego`),
  no en globales. `crear_servidor(puerto=0)` para aislar pruebas.
- La partida abierta se rehidrata de la DB (`_rehidratar`), no se pierde al reiniciar.
- `web/static/` — sin librerías. `app.js` (jugador), `admin.js` (panel en `/admin`).

## Reglas que no hay que romper
- El monedero NO convierte unidades: si le llega un float, **lanza error** a propósito.
- Cobrar la apuesta y dar el cartón van juntos; si falla el cobro no queda cartón vendido.
- `test_bingo.py` y `test_retiros.py` necesitan `Almacen(":memory:")` en `setUp` y
  `almacen.cerrar()` en `tearDown` (si no, SQLite se queja al cerrar).

## Pruebas
226 tests: `python3 -m unittest discover -s tests -t .` (necesita `tests/__init__.py`).

## DESPLEGADO EN RENDER (2026-11-07)
- **URL pública: https://bingopiramide777.onrender.com** (live, HTTP 200).
- Servicio Render `bingopiramide777`, id **`srv-dbnn2upsrm7s739tio40`**, owner `tea-d737nuvkijhs73dbvnb0`
  (equipo TakTak-App), repo GitHub público, rama `main`, autoDeploy sí, plan **free**, región oregon.
- Creado por API con `$TAKTAKapikey` (la key SÍ puede crear servicios). `POST /v1/services` exige
  `buildCommand` no vacío → `pip install -r requirements.txt` (el repo no tiene dependencias).
- Env vars puestas: BINGO_ADMIN_EMAIL, GMAIL_USER, BINGO_ADMIN_CLAVE, GROQ_API_KEY, PYTHON_VERSION.
- **PROBLEMA GRAVE: sin disco persistente (plan free no lo permite).** La base de datos
  (`bingo777.db`) vive en el sistema de ficheros efímero: **cada deploy o reinicio borra TODAS
  las cuentas, saldos, salas, depósitos y retiros**. Además el plan free **duerme el servicio
  a los 15 min sin visitas** (tarda ~30s en despertar). Para producción de verdad: plan de pago
  + disco montado en `/var/data` + `BINGO_DB=/var/data/bingo777.db` (ya previsto en `render.yaml`).
- La app arranca y responde SIN claves (Glenis y correo son opcionales): probado con
  `env -u GROQ_API_KEY`. Si falta `BINGO_ADMIN_CLAVE` genera una aleatoria y la imprime en el log.
- `GET /v1/repos` NO existe en la API de Render (404); los logs por API tampoco (`/logs` 404).

## Salas y economía del bingo (2026-11-07)
- **Modelo copiado de Juegoactivo** (verificado en su web): 3 salas de la casa (Dubai/Roma/
  Estelar) con precio propio, 3 modos (Normal/Cartón lleno/Competencia) y **salas
  personalizadas de jugadores con 10% de comisión para el anfitrión**. Pago Móvil y
  transferencia; ganancias acreditadas "tras las verificaciones"; retiros a los 4 días.
- **Reparto** (`nucleo/salas.py`, `reparto_del_bote`): ganador **80%** siempre; el 20%
  restante es de la app, y en sala de jugador la mitad (10% del bote) va al anfitrión.
  El 10% sale del margen de la app, NO del premio: el ganador cobra igual en cualquier sala.
  `app = bote - premio - anfitrion` (por construcción cuadra; el resto del redondeo es del
  ganador). Probado con 20.000 botes en `test_salas.py`.
- Salas: máx **3 por jugador**, cartón entre Bs 1 y Bs 500, nombres de la casa reservados.
  El anfitrión cobra su comisión **en el momento** vía `resolver_cantada`.
- `MesaBingo(repartidor=...)`: el reparto se inyecta; el reparto devuelve `anfitrion_correo`
  (no un atributo aparte en la mesa — ese diseño falló y se cambió).
- La partida es **por sala**: `partida(sala_id)`, `almacen.partida_abierta_de(sala)`,
  columna `sala` en `partidas` (con migración). Salas de fábrica en `SALAS_INICIALES`.
- Rutas: `GET /api/salas`, `/api/mis-salas`, `/api/admin/salas`; `POST /api/sala/crear`,
  `/api/sala/cerrar`, `/api/sala/entrar`. `/api/config` expone `modos`.
- UI: selector de salas + sección "Tus salas" en `index.html`; pestaña **Ganancias** en
  `admin.html`. Herramientas de Glenis: `listar_salas`, `ganancias`.
- **BUG RESUELTO (Glenis, 2026-11-07)**: los parámetros **opcionales** de las herramientas
  deben declarar `type: ["string","null"]`. El modelo manda `null` en lo que no usa y Groq
  valida estricto: con `type:"string"` tumba la llamada entera (error 400 "tool call
  validation failed"). Lo arregla el helper `f()` en `esquemas()` automáticamente. No
  volver a declarar opcionales con `type` simple.

## Glenis IA + depósitos (2026-11-07)
- **Glenis IA** (`nucleo/glenis.py` + `nucleo/glenis_herramientas.py`): chat en el panel
  (`/api/admin/glenis`). Modelo **`openai/gpt-oss-120b` de Groq**; clave en `GROQ_API_KEY`
  (la del usuario que funciona es **`$Asistente`**; `$IAasistenteGlenis` está INVÁLIDA, 401).
  Cloudflare bloquea el UA de Python: hay que mandar `User-Agent` propio. El plan gratuito
  limita **8000 tokens/minuto** → `_pedir` reintenta leyendo "try again in X" del 429.
  10 herramientas; las que tocan dinero se anotan a nombre de "Glenis IA".
  **El premio NO se paga solo** y el depósito NO se acredita solo: Glenis avisa, la persona paga.
- **Depósitos** (`nucleo/depositos.py`): Pago Móvil/transferencia. El jugador declara monto,
  referencia, banco y día; queda `pendiente` hasta que el admin acredita. Frenos: **misma
  referencia no vale dos veces el mismo día** (índice único parcial), tope diario (cuenta
  pendientes Y acreditados: si no, se salta el tope), y solo 3 días atrás, nunca futuro.
- `_estatico` manda **`Cache-Control: no-store`**: sin esto el navegador servía JS viejo y
  parecía que el chat no funcionaba.
- Ojo al editar `admin.js` con `str.replace`: un bloque se coló DENTRO de `resolverDeposito`.
  Los enganches de eventos van al final, antes de `cargarTodo()`.

## Recuperación de cuenta (2026-11-07)
Tres vías: **código por correo** (6 cifras, 15 min, 1 uso, 5 intentos, tope 3/hora),
**pregunta secreta** (lista cerrada `PREGUNTAS` en `usuarios.py`; respuesta normalizada
sin tildes/mayúsculas) y **restablecer desde el panel** (`/api/admin/restablecer`,
genera `Pepa-xxxxxx`). En las tres, `cambiar_clave()` llama a
`almacen.borrar_sesiones_de()`: **cierra TODAS las sesiones de la cuenta**.
- Correo: `nucleo/correo.py` lee `GMAIL_USER` + `GMAIL_APP_PASSWORD` (contraseña de
  **aplicación**, no la normal). Sin configurar **no miente**: devuelve False, imprime
  el código por consola. Necesita `PYTHONUNBUFFERED=1` para verlo en los logs.
- Anti-enumeración: pedir código de un correo inexistente devuelve lo mismo.
- Las rutas `/api/recuperar/*` van en **do_POST**, no en do_GET.

## Móvil primero
El usuario trabaja desde el teléfono. Botones ≥44 px, `font-size:16px` en inputs
(evita el zoom de iPhone), tablas con scroll horizontal dentro de su caja,
`.mesa` a una columna y cartón antes que el bombo por debajo de 900 px.

## Panel de admin: ventanas y ver cada sala (2026-11-07)
- El panel ya **no es una página larga**: cada apartado (Resumen, Glenis, Depósitos,
  Retiros, Jugadores, Partidas, Salas, Ganancias, Movimientos) se abre como **ventana**
  con su barra y su botón de cerrar. Se abre desde el `nav` o desde la **lanzadera**
  (`#lanzadera`). Cada ventana carga **solo lo suyo** (`VENTANAS[clave].cargar`), así el
  panel no pide datos que no estás mirando. `admin.html` quedó casi vacío: solo la
  lanzadera y `<div id="ventanas">`; las tablas las construye el JS en `cuerpo(clave)`.
  `abiertas` (Set) controla qué ventanas están abiertas; el refresco de 15 s solo toca
  las que están abiertas.
- **Ver cada sala por dentro**: `GET /api/admin/sala?sala=<id>` (solo admin) →
  `Juego.sala_viva()` en `web/servidor.py`. Devuelve sala, estado, jugadores (correo +
  cartones con números y marcas), bolas sacadas, bote, plazas y ganadores.
  En el panel: ventana "Salas en vivo" → botón **Ver sala** por fila.
- **Trampa resuelta**: `sala_viva` debe buscar la partida **en memoria** primero
  (`self.mesa.sala.partidas.values()`); si se rehidrata desde la DB cuando el objeto ya
  está cargado, `abrir_partida` lanza "La partida X ya existe". Y `Juego` **no** tiene
  `_sala_json` (eso vive en el `Manejador`): tiene su propio `_sala_publica`.
- CSS de ventanas: `.lanzadera`, `.ventana*`, `.mesa-jugador*`, `.carton-mini*` en
  `estilos.css`. El `nav` usa `<button data-ventana>` (no enlaces) → hace falta
  `.nav button` en CSS.

## El sistema de juego NO es (todavía) el de Juegoactivo (2026-11-07)
- Faltan las tres cosas que definen a Juegoactivo: **ventanitas de cada jugador sobre la
  mesa**, **bolas que salen solas** (aquí solo salen al pulsar "Sacar bola", no hay hilo
  ni temporizador) y **una partida por sala en pantalla** (hoy hay una sola mesa
  compartida en `_partida_sala`). No hay websockets ni SSE: el front pregunta cada 5 s.
- Lo que sí es bingo real de 75 bolas: cartones 5x5 con rangos B-I-N-G-O, centro libre,
  patrones (`linea_*`, `diagonal`, `esquinas`, `carton_lleno`) y modos normal/
  carton_lleno/competencia.
- **Juegoactivo (solo mirar estructura, nunca copiar)**: `juegoactivo.com` es una landing
  estática; menú: Iniciar sesión / Bingo Activo (Jugar, Más información) / Animalitos
  (Resultados, Jugar, Más información). El juego está en `/jugar/bingo`. Su distintivo
  ("Imagina saber cuántas fichas les faltan a tus oponentes") confirma las ventanitas.
  Derechos: Clickker C.A. — NO copiar diseño ni textos.

## Despliegue (2026-11-08)
- Servicio Render `bingopiramide777` = `srv-dbnn2upsrm7s739tio40`, rama `main`, autoDeploy.
  URL https://bingopiramide777.onrender.com. Plan **free** y **sin disco** → la BD se borra
  en cada deploy (subir a plan de pago + disco `/var/data` para conservarla).
- El servicio **NO se creó desde `render.yaml`** (no es Blueprint): solo tiene 5 env vars.
  Las claves del `render.yaml` (BINGO_PAGO_*, BINGO_ADMIN_CUENTA_*, BINGO_REFERIDO_PCT,
  BINGO_DB) **hay que añadirlas a mano** en Render o recrear el servicio como Blueprint.
- Push: hace falta un **PAT de la cuenta `bingopiramide777`** (admin/push). `$taktak` y
  `$GITHUB_TOKEN` son de `taktakmessenger` y **solo leen** este repo (403 al empujar).
  Empujar con `https://x-access-token:<PAT>@github.com/bingopiramide777/bingopiramide777.git`.
- `main` en GitHub al 2026-11-08: `9e246f3` (multi-país, referidos, Wise, i18n, Postgres).

## Salas de trabajo y comisión de depósitos (2026-11-10)
- **Zulia y Lara** ahora juegan **cartón lleno** (migración `VERSION_JUEGOS` para bases ya
  creadas en `nucleo/salas.py::_subir_juegos_antiguos`).
- **Salas de trabajo** (`salas.es_trabajo`): el anfitrión pone juego y precio desde dentro
  de la sala; se lleva **15 %** del bote (la app el 5 %). Normales: 10 % / 10 %.
  Ruta `POST /api/sala/trabajo` (solo el dueño); `crear` acepta `es_trabajo`.
- **Depósitos**: al acreditar, la app retiene **10 %** (anti-lavado) y guarda `comision` +
  `acreditado` en el depósito. `_economia()` en `web/servidor.py` = bingo + esa comisión.
- Front: `#sala-es-trabajo` en el form, `#dialogo-trabajo`/`#form-trabajo`, aviso
  `#aviso-carton-lleno`, CSS `.sala-tarjeta--trabajo`/`.interruptor`/`.aviso-carton-lleno`.
- Detalle en `.openhands/memory/2026-11-10.md`.

## Billeteras de cripto (2026-11-10)
- Vincular billetera (EVM/Solana) firmando un mensaje de un solo uso (caduca 5 min).
  **Solo biblioteca estándar**: `nucleo/firmas.py` (keccak256, secp256k1/ECDSA con
  recuperación, ed25519) y `nucleo/billeteras.py` (desafío + vinculación). Verificado
  contra `eth_account`/PyNaCl **solo en local** (jamás al repo). Tabla `billeteras` en
  SQLite y PG. Rutas `/api/billetera`, `/api/billetera/desafio`, `/api/billetera/borrar`.
  Front: apartado `#billetera`; `personal_sign` si hay `window.ethereum`, si no copiar/pegar.
- Pruebas: **425 en verde**. Commit local `74cae3e` en `openhands/billeteras-cripto`.
- **El dominio `bingopiramide777.vip` YA está en Render** (Cloudflare delante; apex y `www`
  → `srv-dbnn2upsrm7s739tio40`, auto-deploy desde `main`). Lo que falta es **empujar**.
- **Bloqueo de push (recurrente)**: `$GITHUB_TOKEN` y la credencial git son de
  `taktakmessenger` → **solo lectura** sobre `bingopiramide777/bingopiramide777`
  (`permissions.push=false`). Hace falta un **PAT fine-grained de `bingopiramide777`**
  (*Contents: read and write*) o que el usuario añada a `taktakmessenger` como colaborador
  con permiso de escritura.

## Pendiente / avisos
Falta pasarela de pago real, verificación de identidad en retiros, límite de
recargas y HTTPS. En Venezuela las apuestas requieren autorización: el usuario
fue avisado. "Pirámide" en un producto financiero tiene mala connotación.
