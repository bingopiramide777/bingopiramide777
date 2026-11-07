# Bingo Pirámide 777

Sala de **bingo de 75 bolas** en línea. Proyecto original: motor propio, diseño
propio, textos propios. Sin dependencias externas — solo Python estándar.

## Qué hace

- **Cartones de 5×5** con las columnas B-I-N-G-O (1-15, 16-30, 31-45, 46-60, 61-75)
  y el centro libre.
- **Bombo de 75 bolas** sin repetición.
- **Patrones de premio**: cinco líneas horizontales, cinco verticales, dos
  diagonales, esquinas y cartón lleno.
- **Cantadas comprobadas**: la mesa valida la cantada contra las bolas sacadas.
  Una cantada falsa se rechaza; no se paga.
- **Bote repartido**: el 80 % va al ganador, el 20 % queda para la casa.
- **Monedero exacto**: todo en céntimos enteros. Nada de decimales flotantes.
- **Cuentas propias**: correo y contraseña con PBKDF2-HMAC-SHA256 (200 000
  iteraciones, sal por usuario). **No hay login con Facebook** ni con ninguna red
  social.

## Cómo se arranca

```bash
BINGO_ADMIN_CLAVE="tu-clave-segura" python3 -m web.servidor
```

Y abre `http://localhost:8000`. Para cambiar el puerto:

```bash
PORT=3000 python3 -m web.servidor
```

La **primera vez** se crea la cuenta de administración
(`bingopiramide777@gmail.com`) con la clave que pongas en `BINGO_ADMIN_CLAVE`.
Si no pones ninguna, se genera una al azar y **se muestra una sola vez** por
consola: guárdala. La base de datos es el fichero `bingo777.db`.

### Variables de entorno

| Variable | Para qué | Por defecto |
|---|---|---|
| `PORT` | Puerto del servidor | `8000` |
| `BINGO_DB` | Ruta del fichero de base de datos | `bingo777.db` |
| `BINGO_ADMIN_EMAIL` | Correo del administrador | `bingopiramide777@gmail.com` |
| `BINGO_ADMIN_CLAVE` | Clave del administrador (solo al crearlo) | aleatoria |

## Cómo se corren las pruebas

```bash
python3 -m unittest discover -s tests -t .
```

## Estructura

```
nucleo/          lo común a todo
  money.py       conversión a céntimos, formato en bolívares
  almacen.py     base de datos SQLite (todo lo que sobrevive al reinicio)
  monedero.py    saldos y movimientos, siempre en céntimos
  usuarios.py    registro, contraseñas, roles y sesiones
  retiros.py     pedir, pagar y rechazar retiros
bingo/           el juego
  cartones.py    cartón, bombo y patrones de premio
  sala.py        partidas, venta de cartones y cantadas
  mesa.py        une la sala con el monedero (cobra y paga)
web/             servidor e interfaz
  servidor.py    http.server + API
  static/        interfaz del jugador y panel de administración
tests/           pruebas (87)
```

## Panel de administración

Entra en `http://localhost:8000/admin` con la cuenta de administración. Desde ahí:

- **Resumen**: jugadores, dinero en cuentas, retiros pendientes, apostado, pagado y margen.
- **Retiros**: pagar o rechazar. Rechazar **devuelve el dinero** al jugador.
- **Jugadores**: ver saldos, ajustar saldo a mano, activar o desactivar cuentas.
- **Partidas**: cartones, bolas y premio de cada partida.
- **Movimientos**: todos los movimientos de dinero, con su rastro.

## Retiros

El jugador pide un retiro y el dinero **se descuenta al pedirlo** (así no puede
pedir dos veces el mismo saldo). El administrador lo paga o lo rechaza:

- **Pagar**: solo marca el retiro como pagado. No vuelve a mover el saldo.
- **Rechazar**: devuelve el dinero al saldo del jugador.

Un retiro solo se puede resolver una vez. Si dos administradores pulsan a la vez,
solo uno cobra.

## Publicarlo en internet

El proyecto incluye `render.yaml` para Render. Los pasos:

1. Sube el código a GitHub (ya está en `bingopiramide777/bingopiramide777`).
2. En Render, **New → Blueprint** y elige el repositorio.
3. Cuando pregunte por `BINGO_ADMIN_CLAVE`, pon una clave tuya.
4. Listo. La base de datos queda en un disco persistente (`/var/data`), así que
   los saldos sobreviven a los reinicios.

**Antes de aceptar dinero real, lee el aviso de abajo.**

## Cambiar las reglas

- **Precio del cartón**: `web/servidor.py`, en `Juego.partida()` (por defecto Bs 10,00).
- **Reparto del bote**: `MesaBingo(reparto=Decimal("0.80"))`.
- **Patrón de premio**: `Sala.abrir_partida(..., patron="carton_lleno")`. Los
  nombres están en `bingo/cartones.py` (`PATRONES`).
- **Apuesta mínima y máxima**, **horas de sorteo**: en `Reglas` (ver historial
  del proyecto).

## API

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/api/salud` | Estado del servicio |
| GET | `/api/partida` | Vista pública de la partida actual |
| GET | `/api/saldo` | Saldo del jugador (requiere sesión) |
| GET | `/api/historial` | Movimientos del jugador (requiere sesión) |
| POST | `/api/registro` | Crear cuenta: `correo`, `clave`, `nombre` |
| POST | `/api/entrar` | Entrar: `correo`, `clave` → `token` |
| POST | `/api/recargar` | Añadir saldo: `importe` |
| POST | `/api/carton` | Comprar cartón |
| POST | `/api/bola` | Sacar bola |
| POST | `/api/bingo` | Cantar bingo: `carton` |

Las rutas con sesión llevan la cabecera `Authorization: Bearer <token>`.

## Lo que este proyecto NO es

- **No es una copia** de ninguna otra plataforma. El diseño, los textos y el
  código se han escrito desde cero.
- **No pide iniciar sesión con Facebook**, ni con ninguna red social.
- **No tiene pasarela de pago real.** Las recargas son internas: quien lo ponga
  en producción tiene que conectar su propio cobro.

## Antes de poner esto en producción

Aviso honesto, porque es importante:

- **Comprueba la normativa de tu país.** En Venezuela las apuestas de lotería y
  los juegos de azar están sujetos a autorización. Opera solo donde puedas
  hacerlo legalmente y con las licencias que te correspondan.
- **Falta pasarela de pago real.** Las recargas son internas: nadie cobra de
  verdad todavía. Conecta tu propio cobro antes de aceptar dinero.
- **Falta verificación de identidad** para los retiros (hoy basta con escribir
  unos datos de cobro).
- **Falta límite de recargas** y protección contra el juego compulsivo.
- **Pon HTTPS** antes de exponerlo en internet.

El juego, el monedero, los retiros, las cuentas y la base de datos funcionan y
están probados. Lo que falta es la pasarela de pago y el cumplimiento legal, y
eso hay que hacerlo con cuidado y con asesoría.
