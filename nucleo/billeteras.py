"""Billeteras de cripto vinculadas a una cuenta, con firma de por medio.

El jugador conecta MetaMask, Phantom o cualquier otra billetera y firma un
mensaje. La firma la comprueba ``nucleo.firmas`` (secp256k1 y ed25519 a mano,
sin dependencias). Solo si la firma es de esa dirección se ata la billetera a la
cuenta: así nadie puede apuntarse la dirección de otro.

El mensaje que se firma lleva un código de un solo uso (el desafío) que caduca,
para que una firma vieja no valga dos veces ni sirva para otra cuenta.

Este módulo no mueve dinero ni pide claves privadas: la billetera firma en su
propia app y aquí solo se guarda la dirección pública.
"""

from __future__ import annotations

import json
import secrets
import time

from .almacen import Almacen
from .firmas import ErrorDeBilletera, detectar_red, red_de_ficha, verificar_firma

# El código del desafío dura cinco minutos: tiempo de sobra para firmar.
MINUTOS_DESAFIO = 5
PREFIJO_DESAFIO = "billetera_desafio:"

# Lo que se firma. El dominio va dentro para que la firma no sirva en otro sitio.
PLANTILLA = (
    "Bingo Pirámide 777\n"
    "Vinculación de billetera\n\n"
    "Correo: {correo}\n"
    "Código: {nonce}\n\n"
    "Firmar este mensaje no cuesta gas ni mueve dinero."
)


class ErrorDeBilleteraVinculada(ValueError):
    """No se pudo vincular la billetera."""


def mensaje_de_desafio(correo: str, nonce: str) -> str:
    return PLANTILLA.format(correo=correo, nonce=nonce)


def _normalizar_direccion(direccion: str) -> str:
    direccion = (direccion or "").strip()
    if not direccion:
        raise ErrorDeBilleteraVinculada("Falta la dirección de la billetera.")
    return direccion


def _de_hex(texto: str) -> bytes:
    texto = (texto or "").strip()
    if texto.startswith(("0x", "0X")):
        texto = texto[2:]
    if len(texto) % 2 or not texto:
        raise ErrorDeBilleteraVinculada("La firma no tiene buena pinta.")
    try:
        return bytes.fromhex(texto)
    except ValueError:
        raise ErrorDeBilleteraVinculada("La firma no tiene buena pinta.")


class Billeteras:
    """Guarda qué billetera (red + dirección) tiene cada cuenta."""

    def __init__(self, almacen: Almacen) -> None:
        self.almacen = almacen

    # -- desafíos --

    def desafio(self, correo: str) -> dict:
        """Crea (o rehace) el desafío de firma de una cuenta."""
        correo = (correo or "").strip().lower()
        if not correo:
            raise ErrorDeBilleteraVinculada("Hace falta un correo.")
        nonce = secrets.token_hex(16)
        caduca = time.time() + MINUTOS_DESAFIO * 60
        self.almacen.guardar_meta(PREFIJO_DESAFIO + correo,
                                  json.dumps({"nonce": nonce, "caduca": caduca}))
        return {"nonce": nonce, "caduca": caduca,
                "mensaje": mensaje_de_desafio(correo, nonce)}

    def _desafio_vivo(self, correo: str) -> str:
        crudo = self.almacen.meta(PREFIJO_DESAFIO + correo)
        if not crudo:
            raise ErrorDeBilleteraVinculada("Pide primero el mensaje para firmar.")
        try:
            datos = json.loads(crudo)
        except ValueError:
            raise ErrorDeBilleteraVinculada("Pide primero el mensaje para firmar.")
        if float(datos.get("caduca", 0)) < time.time():
            raise ErrorDeBilleteraVinculada("El mensaje de firma caducó. Pídelo otra vez.")
        return str(datos.get("nonce", ""))

    def _consumir_desafio(self, correo: str) -> None:
        self.almacen.guardar_meta(PREFIJO_DESAFIO + correo, "")

    # -- vinculación --

    def vincular(self, correo: str, direccion: str, firma: str,
                 red: str = "") -> dict:
        """Comprueba la firma y guarda la billetera si es de esa dirección."""
        correo = (correo or "").strip().lower()
        if self.almacen.usuario(correo) is None:
            raise ErrorDeBilleteraVinculada(f"No existe la cuenta {correo}.")
        direccion = _normalizar_direccion(direccion)
        nonce = self._desafio_vivo(correo)
        mensaje = mensaje_de_desafio(correo, nonce)
        try:
            red_normal = red_de_ficha(red, direccion)
        except ErrorDeBilletera as exc:
            raise ErrorDeBilleteraVinculada(str(exc))
        try:
            vale = verificar_firma(red_normal, direccion, mensaje, _de_hex(firma))
        except ErrorDeBilletera as exc:
            raise ErrorDeBilleteraVinculada(str(exc))
        if not vale:
            raise ErrorDeBilleteraVinculada(
                "La firma no corresponde a esa billetera. Vuelve a intentarlo.")
        self._consumir_desafio(correo)
        self.almacen.guardar_billetera(correo, red_normal, direccion)
        return {"correo": correo, "red": red_normal, "direccion": direccion,
                "configurada": True}

    # -- consulta --

    def de(self, correo: str) -> dict | None:
        fila = self.almacen.billetera((correo or "").strip().lower())
        if fila is None:
            return None
        return {"correo": fila["correo"], "red": fila["red"],
                "direccion": fila["direccion"], "creada": fila["creada"],
                "configurada": True}

    def borrar(self, correo: str) -> None:
        self.almacen.borrar_billetera((correo or "").strip().lower())

    @staticmethod
    def red_valida(direccion: str) -> str:
        return detectar_red(direccion)
