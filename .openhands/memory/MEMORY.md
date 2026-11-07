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
114 tests: `python3 -m unittest discover -s tests -t .` (necesita `tests/__init__.py`).

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
