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
python3 -m web.servidor
```

Y abre `http://localhost:8000`. Para cambiar el puerto:

```bash
PORT=3000 python3 -m web.servidor
```

## Cómo se corren las pruebas

```bash
python3 -m unittest discover -s tests -t .
```

## Estructura

```
nucleo/          dinero exacto, monedero y usuarios (lo común)
  money.py       conversión a céntimos, formato en bolívares
  monedero.py    saldos y movimientos, siempre en céntimos
  usuarios.py    registro, contraseñas y sesiones
bingo/           el juego
  cartones.py    cartón, bombo y patrones de premio
  sala.py        partidas, venta de cartones y cantadas
  mesa.py        une la sala con el monedero (cobra y paga)
web/             servidor y interfaz
  servidor.py    http.server + API
  static/        interfaz (HTML, CSS y JavaScript, sin librerías)
tests/           pruebas
```

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
- **Los saldos viven en memoria.** Al reiniciar el servidor se pierden. Antes de
  aceptar dinero real hay que guardar cuentas y movimientos en una base de datos.
- **Falta control de acceso por administrador** para ver las partidas y los pagos.
- **Falta límite de recargas y retiros**, y verificación de identidad.
- **Añade HTTPS** antes de exponerlo en internet.

El juego, el monedero y las cuentas funcionan y están probados. Lo que falta es
la parte de dinero real, y eso hay que hacerlo con cuidado y con asesoría.
