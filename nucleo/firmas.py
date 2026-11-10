"""Verificación de firmas de billeteras de cripto, con la biblioteca estándar.

El jugador conecta su billetera (MetaMask, Phantom, Trust, Rabby…) y firma un
mensaje. Aquí se comprueba que la firma es de verdad de esa billetera, para poder
atar la dirección a su cuenta sin que nadie pueda suplantarla.

El proyecto no tiene dependencias (ni ``web3``, ni ``eth-account``, ni
``pynacl``), así que las cuentas se hacen a mano:

- **secp256k1 + ECDSA**: redes de Ethereum y compatibles (EVM). El mensaje se
  firma con el prefijo estándar ``\\x19Ethereum Signed Message`` (lo que hace
  ``personal_sign``) y la dirección se recupera de la firma. La dirección
  Ethereum es el último tramo de 20 bytes del ``keccak256`` de la clave pública.
- **ed25519**: red de Solana. El mensaje se firma tal cual (utf-8), como hace
  Phantom.

Todo se apoya en ``hashlib`` (SHA-512 para ed25519 y una implementación de
``keccak256`` para Ethereum) y en aritmética entera de Python, que es exacta.

Este módulo **solo verifica**. No guarda claves, no mueve dinero y no habla con
la red: solo responde "sí, esa firma es de esa dirección".
"""

from __future__ import annotations

import hashlib

# --- direcciones y redes ---------------------------------------------------

REDES = {
    "evm": "Ethereum y compatibles (MetaMask, Rabby, Trust…)",
    "solana": "Solana (Phantom, Solflare…)",
}

# Etiquetas de red aceptadas en las fichas de cobro y en el frontend.
ALIAS_RED = {
    "eth": "evm", "ethereum": "evm", "evm": "evm", "erc20": "evm",
    "bsc": "evm", "polygon": "evm", "matic": "evm", "arbitrum": "evm",
    "optimism": "evm", "base": "evm", "avalanche": "evm", "avax": "evm",
    "sol": "solana", "solana": "solana",
}


class ErrorDeBilletera(ValueError):
    """La dirección o la firma no son válidas."""


# --- keccak256 (Ethereum usa keccak, no el SHA-3 con relleno NIST) ---------

_MASK64 = (1 << 64) - 1

_KECCAK_RC = (
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
)

_KECCAK_ROT = (
    (0, 36, 3, 41, 18),
    (1, 44, 10, 45, 2),
    (62, 6, 43, 15, 61),
    (28, 55, 25, 21, 56),
    (27, 20, 39, 8, 14),
)


def _rot(v: int, n: int) -> int:
    if n == 0:
        return v & _MASK64
    return ((v << n) | (v >> (64 - n))) & _MASK64


def _keccak_f(state: list) -> None:
    for rc in _KECCAK_RC:
        c = [state[x][0] ^ state[x][1] ^ state[x][2] ^ state[x][3] ^ state[x][4]
             for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rot(c[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                state[x][y] ^= d[x]
        b = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                b[y][(2 * x + 3 * y) % 5] = _rot(state[x][y], _KECCAK_ROT[x][y])
        for x in range(5):
            for y in range(5):
                state[x][y] = b[x][y] ^ ((~b[(x + 1) % 5][y] & _MASK64)
                                         & b[(x + 2) % 5][y])
        state[0][0] ^= rc


def keccak256(datos: bytes) -> bytes:
    """keccak-256 (el de Ethereum)."""
    tasa = 136  # 1088 bits
    relleno = bytearray(datos)
    relleno.append(0x01)
    while len(relleno) % tasa != 0:
        relleno.append(0x00)
    relleno[-1] ^= 0x80

    estado = [[0] * 5 for _ in range(5)]
    for off in range(0, len(relleno), tasa):
        bloque = relleno[off:off + tasa]
        for i in range(tasa // 8):
            carril = int.from_bytes(bloque[i * 8:(i + 1) * 8], "little")
            estado[i % 5][i // 5] ^= carril
        _keccak_f(estado)

    salida = bytearray()
    for i in range(4):  # 4 carriles = 32 bytes
        salida += estado[i % 5][i // 5].to_bytes(8, "little")
    return bytes(salida)


# --- secp256k1 + ECDSA (Ethereum y compatibles) ----------------------------

_SECP_P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
_SECP_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
_SECP_G = (0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
           0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8)


def _secp_inv(a: int, m: int) -> int:
    return pow(a, m - 2, m)


def _secp_suma(p, q):
    if p is None:
        return q
    if q is None:
        return p
    x1, y1 = p
    x2, y2 = q
    if x1 == x2 and (y1 + y2) % _SECP_P == 0:
        return None
    if p == q:
        lam = (3 * x1 * x1) * _secp_inv(2 * y1, _SECP_P) % _SECP_P
    else:
        lam = (y2 - y1) * _secp_inv(x2 - x1, _SECP_P) % _SECP_P
    x3 = (lam * lam - x1 - x2) % _SECP_P
    y3 = (lam * (x1 - x3) - y1) % _SECP_P
    return (x3, y3)


def _secp_mul(k: int, p):
    r = None
    while k:
        if k & 1:
            r = _secp_suma(r, p)
        p = _secp_suma(p, p)
        k >>= 1
    return r


def _secp_sqrt(a: int):
    """Raíz cuadrada módulo p (p ≡ 3 mod 4)."""
    r = pow(a, (_SECP_P + 1) // 4, _SECP_P)
    return r if r * r % _SECP_P == a % _SECP_P else None


def _recuperar_pubkey(z: int, r: int, s: int, recid: int):
    """Clave pública que produjo la firma (r, s) del hash z, con recid 0..3."""
    if not (1 <= r < _SECP_N and 1 <= s < _SECP_N):
        return None
    x = r + (recid // 2) * _SECP_N
    if x >= _SECP_P:
        return None
    alfa = (pow(x, 3, _SECP_P) + 7) % _SECP_P
    beta = _secp_sqrt(alfa)
    if beta is None:
        return None
    y = beta if (beta & 1) == (recid & 1) else _SECP_P - beta
    r_enc = (x, y)
    r_inv = pow(r, -1, _SECP_N)
    u1 = (-z * r_inv) % _SECP_N
    u2 = (s * r_inv) % _SECP_N
    return _secp_suma(_secp_mul(u1, _SECP_G), _secp_mul(u2, r_enc))


def _direccion_evm(clave_publica) -> str:
    """Dirección Ethereum (0x…) a partir del punto de la clave pública."""
    x, y = clave_publica
    crudo = x.to_bytes(32, "big") + y.to_bytes(32, "big")
    return "0x" + keccak256(crudo)[-20:].hex()


def mensaje_evm(mensaje: str) -> bytes:
    """El texto que de verdad se firma en ``personal_sign``."""
    cuerpo = mensaje.encode("utf-8")
    return b"\x19Ethereum Signed Message:\n" + str(len(cuerpo)).encode() + cuerpo


def verificar_evm(direccion: str, mensaje: str, firma: bytes) -> bool:
    if len(firma) != 65:
        raise ErrorDeBilletera("La firma de Ethereum debe tener 65 bytes.")
    r = int.from_bytes(firma[:32], "big")
    s = int.from_bytes(firma[32:64], "big")
    z = int.from_bytes(keccak256(mensaje_evm(mensaje)), "big")
    # No se usa el byte "v": se prueban los dos posibles recid y se acepta el que
    # reconstruye la dirección pedida. Así vale con v=0/1 y con v=27/28.
    pedida = direccion.lower()
    for recid in (0, 1):
        pub = _recuperar_pubkey(z, r, s, recid)
        if pub is not None and _direccion_evm(pub).lower() == pedida:
            return True
    return False


# --- ed25519 (Solana) ------------------------------------------------------

_ED_P = 2 ** 255 - 19
_ED_L = 2 ** 252 + 27742317777372353535851937790883648493
_ED_D = (-121665 * pow(121666, _ED_P - 2, _ED_P)) % _ED_P
_ED_I = pow(2, (_ED_P - 1) // 4, _ED_P)


def _ed_recuperar_x(y: int, signo: int):
    if y >= _ED_P:
        return None
    xx = (y * y - 1) * pow(_ED_D * y * y + 1, _ED_P - 2, _ED_P) % _ED_P
    x = pow(xx, (_ED_P + 3) // 8, _ED_P)
    if (x * x - xx) % _ED_P != 0:
        x = x * _ED_I % _ED_P
    if (x * x - xx) % _ED_P != 0:
        return None
    if x & 1 != signo:
        x = _ED_P - x
    return x


def _ed_descomprimir(datos: bytes):
    if len(datos) != 32:
        return None
    y = int.from_bytes(datos, "little") & ((1 << 255) - 1)
    signo = datos[31] >> 7
    x = _ed_recuperar_x(y, signo)
    if x is None:
        return None
    return (x, y, 1, x * y % _ED_P)


def _ed_suma(p, q):
    x1, y1, z1, t1 = p
    x2, y2, z2, t2 = q
    a = (y1 - x1) * (y2 - x2) % _ED_P
    b = (y1 + x1) * (y2 + x2) % _ED_P
    c = t1 * 2 * _ED_D * t2 % _ED_P
    d = z1 * 2 * z2 % _ED_P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % _ED_P, g * h % _ED_P, f * g % _ED_P, e * h % _ED_P)


def _ed_mul(k: int, p):
    r = (0, 1, 1, 0)  # punto neutro
    while k:
        if k & 1:
            r = _ed_suma(r, p)
        p = _ed_suma(p, p)
        k >>= 1
    return r


def _ed_base():
    by = 4 * pow(5, _ED_P - 2, _ED_P) % _ED_P
    bx = _ed_recuperar_x(by, 0)
    return (bx, by, 1, bx * by % _ED_P)


def _ed_igual(p, q) -> bool:
    x1, y1, z1, _ = p
    x2, y2, z2, _ = q
    if (x1 * z2 - x2 * z1) % _ED_P != 0:
        return False
    return (y1 * z2 - y2 * z1) % _ED_P == 0


def verificar_solana(direccion: str, mensaje: str, firma: bytes) -> bool:
    if len(firma) != 64:
        raise ErrorDeBilletera("La firma de Solana debe tener 64 bytes.")
    try:
        clave = base58_a_bytes(direccion)
    except ErrorDeBilletera:
        return False
    if len(clave) != 32:
        return False
    punto_a = _ed_descomprimir(clave)
    punto_r = _ed_descomprimir(firma[:32])
    if punto_a is None or punto_r is None:
        return False
    s = int.from_bytes(firma[32:], "little")
    if s >= _ED_L:
        return False
    k = int.from_bytes(hashlib.sha512(firma[:32] + clave + mensaje.encode("utf-8"))
                       .digest(), "little") % _ED_L
    izquierda = _ed_mul(s, _ed_base())
    derecha = _ed_suma(punto_r, _ed_mul(k, punto_a))
    return _ed_igual(izquierda, derecha)


# --- base58 (direcciones de Solana) ----------------------------------------

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def base58_a_bytes(texto: str) -> bytes:
    num = 0
    for ch in texto:
        idx = _B58.find(ch)
        if idx < 0:
            raise ErrorDeBilletera("Dirección base58 no válida.")
        num = num * 58 + idx
    cuerpo = num.to_bytes((num.bit_length() + 7) // 8, "big") if num else b""
    ceros = len(texto) - len(texto.lstrip("1"))
    return b"\x00" * ceros + cuerpo


# --- API pública -----------------------------------------------------------

def detectar_red(direccion: str) -> str:
    """Adivina la red de una dirección: ``evm`` o ``solana``."""
    direccion = (direccion or "").strip()
    if direccion.startswith(("0x", "0X")) and len(direccion) == 42:
        try:
            int(direccion[2:], 16)
        except ValueError:
            raise ErrorDeBilletera("Dirección de Ethereum no válida.")
        return "evm"
    try:
        crudo = base58_a_bytes(direccion)
    except ErrorDeBilletera:
        raise ErrorDeBilletera("No se reconoce esa dirección de billetera.")
    if len(crudo) == 32:
        return "solana"
    raise ErrorDeBilletera("No se reconoce esa dirección de billetera.")


def red_de_ficha(red: str, direccion: str) -> str:
    """Normaliza la red que viene en la ficha; si viene vacía, la adivina."""
    clave = (red or "").strip().lower()
    if clave in ALIAS_RED:
        return ALIAS_RED[clave]
    return detectar_red(direccion)


def verificar_firma(red: str, direccion: str, mensaje: str, firma: bytes) -> bool:
    """Comprueba que ``firma`` sobre ``mensaje`` es de ``direccion`` en esa red."""
    red = red_de_ficha(red, direccion)
    if red == "evm":
        return verificar_evm(direccion, mensaje, firma)
    if red == "solana":
        return verificar_solana(direccion, mensaje, firma)
    raise ErrorDeBilletera(f"Red no soportada: {red}")
