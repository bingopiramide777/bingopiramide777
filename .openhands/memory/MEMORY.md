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
196 tests: `python3 -m unittest discover -s tests -t .` (necesita `tests/__init__.py`).

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

## Despliegue
`render.yaml` incluido (disco persistente en `/var/data` para la DB).
Push con `$taktak`; **nunca** con `$GITHUB_TOKEN` (403).

## Pendiente / avisos
Falta pasarela de pago real, verificación de identidad en retiros, límite de
recargas y HTTPS. En Venezuela las apuestas requieren autorización: el usuario
fue avisado. "Pirámide" en un producto financiero tiene mala connotación.
