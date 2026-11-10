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
  usuarios.py    registro, contraseñas, roles, sesiones y recuperación
  correo.py      envío de correos (contraseña de aplicación de Gmail)
  depositos.py   pagos declarados por el jugador (Pago Móvil y transferencia)
  salas.py       salas de bingo y reparto del bote (premio, anfitrión y app)
  firmas.py      verificación de firmas de billeteras (secp256k1 y ed25519)
  billeteras.py  vincula una billetera de cripto a la cuenta con una firma
  glenis.py      el motor de Glenis IA (habla con el modelo)
  glenis_herramientas.py  lo que Glenis puede consultar y hacer
  retiros.py     pedir, pagar y rechazar retiros
bingo/           el juego
  cartones.py    cartón, bombo y patrones de premio
  sala.py        partidas, venta de cartones y cantadas
  mesa.py        une la sala con el monedero (cobra y paga)
web/             servidor e interfaz
  servidor.py    http.server + API
  static/        interfaz del jugador y panel de administración
tests/           pruebas (425)
```

## Cuánto cuesta un cartón y en qué se convierte

El modelo está calcado del de Juegoactivo, que tiene tres salas con precio propio y deja
crear salas a los jugadores con un 10 % de comisión para el anfitrión.

**Salas de la casa** (precio del cartón y modo):

| Sala | Modo | Cartón | Premio al ganador | Se queda la app |
|---|---|---|---|---|
| Dubai | Normal | Bs 5,00 | 80 % del bote | 20 % del bote |
| Roma | Competencia | Bs 10,00 | 80 % del bote | 20 % del bote |
| Estelar | Cartón lleno | Bs 20,00 | 80 % del bote | 20 % del bote |

**Salas de un jugador** (las crea cualquiera, con su nombre y su precio, entre Bs 1 y Bs 500):

| Quién | Cuánto |
|---|---|
| Ganador | 80 % del bote |
| Anfitrión (quien creó la sala) | 10 % del bote |
| Se queda la app | 10 % del bote |

El ganador **cobra lo mismo** juegue donde juegue. El 10 % del anfitrión sale del margen de
la app, no del bolsillo del ganador. Así el anfitrión trae jugadores y la app nunca pierde.

### La cuenta, con un ejemplo

Dos jugadores compran un cartón de Bs 10 en la sala de un particular. El bote son Bs 20:

```
bote                      Bs 20,00
premio al ganador         Bs 16,00   (80 %)
comisión del anfitrión    Bs  2,00   (10 %)
se queda la app           Bs  2,00   (10 %)
                          ────────
suma                      Bs 20,00   cuadra al céntimo
```

Esa comprobación está en las pruebas: `test_el_reparto_nunca_pierde_un_centimo` recorre
20.000 botes distintos, con céntimos raros incluidos, y exige que las tres partes sumen
exactamente el bote. Si algún día alguien toca los porcentajes y descuadra un céntimo,
la prueba lo caza.

## Salas creadas por los jugadores

Cualquiera con cuenta puede crear hasta **3 salas**, con:

- **Nombre** (máximo 30 letras; los nombres de la casa están reservados).
- **Modo**: Normal, Cartón lleno o Competencia.
- **Precio del cartón**: entre Bs 1,00 y Bs 500,00.
- **Pública o privada**.

El anfitrión cobra su 10 % **en el momento** de cada bingo, directo a su monedero: no tiene
que reclamarlo ni esperar. En su pantalla ve un panel con sus salas, los botes que han
movido y lo que lleva ganado.

**Lo que NO puede hacer un anfitrión:** tocar el saldo de nadie, acreditar depósitos ni
pagar premios. Solo cobra su comisión, que la calcula el motor. Ni él ni Glenis firman pagos.

## Glenis IA (asistente de administración)

En el panel, la pestaña **Glenis IA** es un chat para llevar la cuenta. Habla con un modelo
de lenguaje y tiene **herramientas** para mirar y mover cosas de verdad.

**Consulta**: resumen del día, buscar jugador, listar jugadores, depósitos, retiros y partidas.
**Actúa** (queda anotado a su nombre): acreditar o rechazar un depósito, ajustar un saldo,
dejar constancia de un ganador y anotar un pago manual.

Reglas de diseño, y son a propósito:

- **No inventa.** Si no puede comprobarlo, lo dice. Mira los datos antes de responder.
- **El premio no se paga solo.** Glenis deja el aviso; el pago lo hace la persona.
- **El depósito tampoco se acredita solo por una foto.** El jugador lo declara, Glenis y tú
  lo revisáis, y el administrador confirma. La IA ayuda; no firma.
- **Un administrador no es un jugador.** Al contar jugadores, cuenta solo el rol `jugador`.

Configuración: `GROQ_API_KEY` en el entorno (se saca en console.groq.com). Sin clave, el panel
lo dice claro en vez de fallar sin explicación. El plan gratuito de Groq limita los tokens por
minuto; Glenis espera y reintenta en vez de dar error.

## Depósitos (Pago Móvil y transferencia)

Como en Juegoactivo: el jugador paga por fuera desde su banco y **declara** aquí el monto, la
referencia, el banco y el día. El dinero **no se acredita solo**.

Tres frenos, porque aquí es donde se pierde el dinero en estas webs:

1. **La misma referencia no vale dos veces el mismo día.** Si reenvían la misma captura, se
   rechaza. Una referencia rechazada sí se puede volver a usar.
2. **Tope diario por jugador**, contando pendientes y acreditados. Si solo contaran los
   acreditados, se podrían declarar mil sin revisar y saltarse el tope.
3. **Solo se admite declarar pagos de los últimos 3 días**, y nunca con fecha futura.

El administrador comprueba la referencia en su banco y acredita o rechaza. Igual que en los
retiros, un depósito **solo se resuelve una vez**: si dos personas pulsan a la vez, solo una
cobra.

## Recuperación de cuenta

Si un jugador olvida la contraseña, tiene **tres caminos**:

1. **Código por correo.** Escribe su correo, le llega un código de 6 cifras y pone
   una contraseña nueva. El código caduca en 15 minutos, solo sirve una vez y
   aguanta 5 intentos fallidos.
2. **Pregunta secreta.** Si la eligió al registrarse, responde y pone una nueva.
   La respuesta se compara sin mayúsculas, sin tildes y sin espacios de sobra.
3. **El administrador.** En el panel, botón *Restablecer clave*: genera una
   contraseña temporal y se la pasas al jugador.

**En los tres casos se cierran todas las sesiones abiertas de esa cuenta.** Es lo
importante: si alguien te había robado la cuenta, cambiar la contraseña sin cerrar
sesiones no lo echa. Con esto, sí.

### Configurar el correo

El código por correo necesita una **contraseña de aplicación** de Gmail (no tu
contraseña normal). Se genera en `myaccount.google.com/apppasswords` (hace falta
tener activada la verificación en dos pasos).

En Render, añade estas variables de entorno:

| Variable | Valor |
|---|---|
| `GMAIL_USER` | `bingopiramide777@gmail.com` |
| `GMAIL_APP_PASSWORD` | las 16 letras que te da Google |

**Sin esas variables la aplicación no miente**: el correo no se envía, el código
se imprime por consola y la pantalla avisa. Las otras dos formas de recuperar
siguen funcionando igual.

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

## Billeteras de cripto

El jugador puede atar su billetera (MetaMask, Phantom, Trust…) a su cuenta. La
app pide un mensaje con un **código de un solo uso** que caduca a los 5 minutos;
el jugador lo firma en su billetera y pega la dirección y la firma. La app
**verifica la firma** antes de guardar nada, así que nadie puede apuntarse la
dirección de otro.

- La verificación es con la **biblioteca estándar** (`nucleo/firmas.py`):
  secp256k1/ECDSA para Ethereum y compatibles, ed25519 para Solana. No pide claves
  privadas ni mueve dinero: la billetera firma en su propia app.
- Firmar **no cuesta gas**. El mensaje lo dice, para que el jugador no desconfíe.
- En el navegador, si hay una billetera inyectada, el botón "Firmar con mi
  billetera" la usa directo; si no, el jugador copia el mensaje y lo firma a mano.

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
| GET | `/api/billetera` | Billetera de cripto de la cuenta (requiere sesión) |
| POST | `/api/billetera/desafio` | Mensaje para firmar con la billetera (requiere sesión) |
| POST | `/api/billetera` | Vincular: `direccion`, `firma`, `red` (requiere sesión) |
| POST | `/api/billetera/borrar` | Desvincular la billetera (requiere sesión) |

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
