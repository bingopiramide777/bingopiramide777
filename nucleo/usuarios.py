"""Usuarios y sesiones, guardados en la base de datos. Registro propio.

Correo y contraseña con PBKDF2-HMAC-SHA256 y sal por usuario. Nunca en claro, y
la comparación es en tiempo constante. Nada de login con Facebook.

Hay dos roles: 'jugador' y 'admin'. El administrador se crea al arrancar, con el
correo configurado. Nadie puede darse de alta como admin por su cuenta.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from dataclasses import dataclass

from .almacen import Almacen

ITERACIONES = 200_000
LARGO_CLAVE_MINIMO = 8
CORREO_VALIDO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
COMUNES = {"12345678", "123456789", "password", "qwertyui", "contrasena", "11111111"}


class ErrorDeUsuario(ValueError):
    """Registro o entrada no válida."""


def _hash(clave: str, sal: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), sal, ITERACIONES).hex()


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
    if clave.lower() in COMUNES:
        raise ErrorDeUsuario("Esa contraseña es demasiado común.")


@dataclass
class Usuario:
    correo: str
    nombre: str
    rol: str
    activo: bool
    creado: float


@dataclass
class Sesion:
    token: str
    correo: str
    creada: float
    caduca: float


def _usuario(fila) -> Usuario:
    return Usuario(correo=fila["correo"], nombre=fila["nombre"], rol=fila["rol"],
                   activo=bool(fila["activo"]), creado=fila["creado"])


class Usuarios:
    def __init__(self, almacen: Almacen, horas_sesion: int = 12,
                 max_intentos: int = 5, minutos_bloqueo: int = 15) -> None:
        self.almacen = almacen
        self.horas_sesion = horas_sesion
        self.max_intentos = max_intentos
        self.minutos_bloqueo = minutos_bloqueo
        self._intentos: dict[str, tuple[int, float]] = {}

    # -- registro --

    def registrar(self, correo: str, clave: str, nombre: str = "", rol: str = "jugador") -> Usuario:
        correo = (correo or "").strip().lower()
        if not CORREO_VALIDO.match(correo):
            raise ErrorDeUsuario("Ese correo no tiene buena pinta.")
        if self.almacen.usuario(correo):
            raise ErrorDeUsuario("Ya hay una cuenta con ese correo.")
        validar_clave(clave)
        if rol not in ("jugador", "admin"):
            raise ErrorDeUsuario("Rol no válido.")
        self.almacen.crear_usuario(correo, hash_clave(clave), (nombre or "").strip(), rol, time.time())
        return Usuario(correo=correo, nombre=(nombre or "").strip(), rol=rol, activo=True,
                       creado=time.time())

    def asegurar_admin(self, correo: str, clave: str) -> bool:
        """Crea la cuenta de administración si no existe. Devuelve si la creó."""
        correo = (correo or "").strip().lower()
        if self.almacen.usuario(correo):
            return False
        validar_clave(clave)
        self.almacen.crear_usuario(correo, hash_clave(clave), "Administración", "admin", time.time())
        return True

    def usuario(self, correo: str) -> Usuario | None:
        fila = self.almacen.usuario((correo or "").strip().lower())
        return _usuario(fila) if fila else None

    def usuarios(self) -> list[Usuario]:
        return [_usuario(f) for f in self.almacen.usuarios()]

    def es_admin(self, correo: str) -> bool:
        u = self.usuario(correo)
        return bool(u and u.rol == "admin" and u.activo)

    def cambiar_clave(self, correo: str, nueva: str) -> None:
        validar_clave(nueva)
        self.almacen.cambiar_huella(correo.strip().lower(), hash_clave(nueva))

    def activar(self, correo: str, activo: bool) -> None:
        self.almacen.cambiar_activo(correo.strip().lower(), activo)

    # -- entrada --

    def entrar(self, correo: str, clave: str) -> Sesion:
        correo = (correo or "").strip().lower()
        fallos, hasta = self._intentos.get(correo, (0, 0.0))
        ahora = time.time()
        if hasta > ahora:
            raise ErrorDeUsuario(f"Demasiados intentos. Prueba en {int(hasta - ahora)} segundos.")
        fila = self.almacen.usuario(correo)
        if fila is None or not verificar_clave(clave, fila["huella"]):
            fallos += 1
            self._intentos[correo] = (fallos, ahora + self.minutos_bloqueo * 60 if fallos >= self.max_intentos else 0.0)
            raise ErrorDeUsuario("Correo o contraseña incorrectos.")
        if not fila["activo"]:
            raise ErrorDeUsuario("Esa cuenta está desactivada.")
        self._intentos.pop(correo, None)
        token = secrets.token_urlsafe(24)
        caduca = ahora + self.horas_sesion * 3600
        self.almacen.crear_sesion(token, correo, ahora, caduca)
        return Sesion(token=token, correo=correo, creada=ahora, caduca=caduca)

    def sesion(self, token: str) -> Sesion | None:
        if not token:
            return None
        fila = self.almacen.sesion(token)
        if fila is None:
            return None
        if fila["caduca"] < time.time():
            self.almacen.borrar_sesion(token)
            return None
        return Sesion(token=fila["token"], correo=fila["correo"], creada=fila["creada"],
                      caduca=fila["caduca"])

    def salir(self, token: str) -> None:
        self.almacen.borrar_sesion(token)
