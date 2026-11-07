"""Usuarios y sesiones. Registro propio: correo y contraseña. Nada de Facebook.

Las contraseñas se guardan con PBKDF2-HMAC-SHA256 y sal por usuario. Nunca en
claro, y la comparación es en tiempo constante para no filtrar información.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from dataclasses import dataclass, field

ITERACIONES = 200_000
LARGO_CLAVE_MINIMO = 8
CORREO_VALIDO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ErrorDeUsuario(ValueError):
    """Registro o entrada no válida."""


def _hash(clave: str, sal: bytes) -> str:
    d = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), sal, ITERACIONES)
    return d.hex()


def hash_clave(clave: str) -> str:
    """Devuelve 'sal$huella'. La sal es nueva en cada llamada."""
    sal = secrets.token_bytes(16)
    return f"{sal.hex()}${_hash(clave, sal)}"


def verificar_clave(clave: str, guardado: str) -> bool:
    try:
        sal_hex, huella = guardado.split("$", 1)
        sal = bytes.fromhex(sal_hex)
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(_hash(clave, sal), huella)


def validar_clave(clave: str) -> None:
    if not isinstance(clave, str) or len(clave) < LARGO_CLAVE_MINIMO:
        raise ErrorDeUsuario(f"La contraseña debe tener al menos {LARGO_CLAVE_MINIMO} caracteres.")
    if clave.lower() in {"12345678", "password", "qwertyui"}:
        raise ErrorDeUsuario("Esa contraseña es demasiado común.")


@dataclass
class Usuario:
    correo: str
    huella: str
    nombre: str = ""
    creado: float = field(default_factory=time.time)
    activo: bool = True


@dataclass
class Sesion:
    token: str
    correo: str
    creada: float
    caduca: float


class Usuarios:
    """Registro de usuarios y sesiones. En memoria; se puede volcar a disco aparte."""

    def __init__(self, horas_sesion: int = 12, max_intentos: int = 5, minutos_bloqueo: int = 15) -> None:
        self.usuarios: dict[str, Usuario] = {}
        self.sesiones: dict[str, Sesion] = {}
        self.horas_sesion = horas_sesion
        self.max_intentos = max_intentos
        self.minutos_bloqueo = minutos_bloqueo
        self._intentos: dict[str, tuple[int, float]] = {}

    # -- registro --

    def registrar(self, correo: str, clave: str, nombre: str = "") -> Usuario:
        correo = (correo or "").strip().lower()
        if not CORREO_VALIDO.match(correo):
            raise ErrorDeUsuario("Ese correo no tiene buena pinta.")
        if correo in self.usuarios:
            raise ErrorDeUsuario("Ya hay una cuenta con ese correo.")
        validar_clave(clave)
        usuario = Usuario(correo=correo, huella=hash_clave(clave), nombre=nombre.strip())
        self.usuarios[correo] = usuario
        return usuario

    # -- entrada --

    def entrar(self, correo: str, clave: str) -> Sesion:
        correo = (correo or "").strip().lower()
        fallos, hasta = self._intentos.get(correo, (0, 0.0))
        ahora = time.time()
        if hasta > ahora:
            raise ErrorDeUsuario(f"Demasiados intentos. Prueba en {int(hasta - ahora)} segundos.")
        usuario = self.usuarios.get(correo)
        if usuario is None or not verificar_clave(clave, usuario.huella):
            fallos += 1
            self._intentos[correo] = (fallos, ahora + self.minutos_bloqueo * 60 if fallos >= self.max_intentos else 0.0)
            raise ErrorDeUsuario("Correo o contraseña incorrectos.")
        self._intentos.pop(correo, None)
        token = secrets.token_urlsafe(24)
        sesion = Sesion(token=token, correo=correo, creada=ahora, caduca=ahora + self.horas_sesion * 3600)
        self.sesiones[token] = sesion
        return sesion

    def sesion(self, token: str) -> Sesion | None:
        sesion = self.sesiones.get(token)
        if sesion is None:
            return None
        if sesion.caduca < time.time():
            self.sesiones.pop(token, None)
            return None
        return sesion

    def salir(self, token: str) -> None:
        self.sesiones.pop(token, None)
