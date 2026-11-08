"""Cifrado de datos sensibles con la biblioteca estándar.

Los datos de cobro de un jugador (banco, teléfono, cédula, cashtag) no pueden
quedar en claro en la base de datos: quien lea el fichero de SQLite se llevaría
los datos bancarios de todo el mundo. Aquí se cifran antes de guardarlos.

El proyecto no tiene dependencias, así que no se usa ``cryptography``. Se
construye un cifrado autenticado con lo que trae Python:

- **Clave**: 32 bytes. Sale de ``BINGO_DATOS_CLAVE`` si está puesta; si no, se
  genera una vez y se guarda en la tabla ``meta``. Así funciona recién instalado
  y sobrevive a los reinicios, sin obligar a configurar nada.
- **Confidencialidad**: se genera un flujo (keystream) con HMAC-SHA256 en modo
  contador y se hace XOR con el mensaje. Es un cifrado de flujo, y el nonce es
  nuevo en cada cifrado, así que el mismo texto no da dos veces el mismo cifrado.
- **Integridad**: se añade una etiqueta HMAC sobre el texto cifrado. Si alguien
  toca la base de datos, el descifrado falla en vez de devolver basura.

Esto es más que suficiente para lo que hay que proteger aquí (que un volcado de
la base de datos no exponga los datos bancarios). No sustituye a un KMS, pero
tampoco mete una dependencia nueva en un proyecto que presume de no tenerlas.

**Importante**: si se pierde la clave (se borra la tabla ``meta`` y no está la
variable de entorno), los datos de cobro ya no se pueden leer. Quedan cifrados e
ilegibles a propósito: es lo que debe pasar cuando falta la llave.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets

LARGO_CLAVE = 32
LARGO_NONCE = 16
VARIABLE_CLAVE = "BINGO_DATOS_CLAVE"
CLAVE_EN_META = "datos_cobro_clave"


class ErrorDeCifrado(ValueError):
    """No se pudo cifrar o descifrar: clave que falta o datos manipulados."""


def _keystream(clave: bytes, nonce: bytes, largo: int) -> bytes:
    """Genera ``largo`` bytes de flujo con HMAC-SHA256 en modo contador.

    A cada bloque se le pasa ``nonce || contador``. La clave se usa solo dentro
    del HMAC, nunca se mezcla directamente con el mensaje.
    """
    salida = bytearray()
    contador = 0
    while len(salida) < largo:
        bloque = hmac.new(clave, nonce + contador.to_bytes(8, "big"), hashlib.sha256).digest()
        salida.extend(bloque)
        contador += 1
    return bytes(salida[:largo])


def _etiqueta(clave: bytes, nonce: bytes, cifrado: bytes) -> bytes:
    return hmac.new(clave, nonce + cifrado, hashlib.sha256).digest()


def cifrar(texto: str, clave: bytes) -> str:
    """Cifra un texto y devuelve base64(nonce || cifrado || etiqueta)."""
    if not isinstance(clave, (bytes, bytearray)) or len(clave) != LARGO_CLAVE:
        raise ErrorDeCifrado("La clave tiene que ser de 32 bytes.")
    datos = (texto or "").encode("utf-8")
    nonce = secrets.token_bytes(LARGO_NONCE)
    flujo = _keystream(clave, nonce, len(datos))
    cifrado = bytes(a ^ b for a, b in zip(datos, flujo))
    paquete = nonce + cifrado + _etiqueta(clave, nonce, cifrado)
    return base64.b64encode(paquete).decode("ascii")


def descifrar(paquete_b64: str, clave: bytes) -> str:
    """Descifra lo que devolvió ``cifrar``. Falla si los datos se tocaron."""
    if not isinstance(clave, (bytes, bytearray)) or len(clave) != LARGO_CLAVE:
        raise ErrorDeCifrado("La clave tiene que ser de 32 bytes.")
    if not paquete_b64:
        return ""
    try:
        paquete = base64.b64decode(paquete_b64.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError):
        raise ErrorDeCifrado("Los datos cifrados no están bien formados.") from None
    if len(paquete) < LARGO_NONCE + 32:
        raise ErrorDeCifrado("Los datos cifrados están incompletos.")
    nonce = paquete[:LARGO_NONCE]
    etiqueta = paquete[-32:]
    cifrado = paquete[LARGO_NONCE:-32]
    esperada = _etiqueta(clave, nonce, cifrado)
    # Comparación en tiempo constante: no se filtra por dónde falla.
    if not hmac.compare_digest(etiqueta, esperada):
        raise ErrorDeCifrado("Los datos cifrados fueron alterados o la clave no es la misma.")
    flujo = _keystream(clave, nonce, len(cifrado))
    return bytes(a ^ b for a, b in zip(cifrado, flujo)).decode("utf-8")


def clave_desde_entorno() -> bytes | None:
    """Lee la clave de ``BINGO_DATOS_CLAVE`` (en hex o base64). None si no está."""
    crudo = os.environ.get(VARIABLE_CLAVE) or ""
    if not crudo:
        return None
    return clave_desde_texto(crudo)


def clave_desde_texto(crudo: str) -> bytes:
    """Interpreta una clave en texto: hex de 64 caracteres, base64, o texto libre."""
    crudo = crudo.strip()
    if len(crudo) == 64:
        try:
            return bytes.fromhex(crudo)
        except ValueError:
            pass
    try:
        datos = base64.b64decode(crudo.encode("ascii"), validate=True)
        if len(datos) == LARGO_CLAVE:
            return datos
    except (ValueError, UnicodeEncodeError):
        pass
    # Cualquier otro texto: se deriva una clave de 32 bytes. Así una frase puesta
    # a mano en Render también sirve, sin obligar a generar bytes exactos.
    return hashlib.sha256(crudo.encode("utf-8")).digest()


def clave_nueva() -> str:
    """Una clave nueva en hex, para poner en ``BINGO_DATOS_CLAVE``."""
    return secrets.token_bytes(LARGO_CLAVE).hex()
