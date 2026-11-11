"""Usuarios y sesiones, guardados en la base de datos. Registro propio.

Correo y contraseña con PBKDF2-HMAC-SHA256 y sal por usuario. Nunca en claro, y
la comparación es en tiempo constante. Nada de login con Facebook.

Hay dos roles: 'jugador' y 'admin'. El administrador se crea al arrancar, con el
correo configurado. Nadie puede darse de alta como admin por su cuenta.
"""

from __future__ import annotations

import base64
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

# Preguntas para recuperar la cuenta sin depender del correo. Son fáciles de
# recordar y difíciles de adivinar para quien no sea el dueño.
PREGUNTAS = (
    "¿Cómo se llamaba tu primera mascota?",
    "¿En qué ciudad nació tu madre?",
    "¿Cómo se llamaba tu mejor amigo de la infancia?",
    "¿Cuál fue tu primer trabajo?",
    "¿Cuál es tu comida favorita?",
    "¿Cómo se llamaba tu primera escuela?",
)

MINUTOS_CODIGO = 15          # cuánto vale un código
CODIGOS_POR_HORA = 3         # tope de códigos pedidos por hora y cuenta
INTENTOS_CODIGO = 5          # intentos antes de anular el código


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


# La foto de perfil viaja como data URL en base64. Se admiten solo imágenes
# pequeñas (una cara, no un póster) para no llenar la base de datos.
FOTO_MAX_BYTES = 300_000
_FOTO_VALIDA = re.compile(
    r"^data:image/(png|jpeg|jpg|webp|gif);base64,([A-Za-z0-9+/]+={0,2})$")


def validar_foto(foto: str) -> str:
    """Devuelve la foto limpia o lanza si no vale. Vacío = quitarla."""
    foto = (foto or "").strip()
    if not foto:
        return ""
    coincidencia = _FOTO_VALIDA.match(foto)
    if not coincidencia:
        raise ErrorDeUsuario("La foto tiene que ser una imagen (PNG, JPG, WEBP o GIF).")
    datos = coincidencia.group(2)
    if len(datos) * 3 // 4 > FOTO_MAX_BYTES:
        raise ErrorDeUsuario("La foto es demasiado grande (máximo 300 KB).")
    try:
        base64.b64decode(datos, validate=True)
    except (ValueError, base64.binascii.Error):
        raise ErrorDeUsuario("La foto no se pudo leer.") from None
    return foto


@dataclass
class Usuario:
    correo: str
    nombre: str
    rol: str
    activo: bool
    creado: float
    comision_pct: int = -1     # % de comisión de anfitrión; -1 = el de por defecto
    verificado: bool = True    # False = falta confirmar el correo
    foto: str = ""             # foto de perfil (data URL) o vacío


@dataclass
class Sesion:
    token: str
    correo: str
    creada: float
    caduca: float


def _normalizar_respuesta(respuesta: str) -> str:
    """Las respuestas se comparan sin mayúsculas, sin tildes y sin espacios de sobra.

    Nadie escribe su respuesta igual dos veces, y perder la cuenta por una tilde
    sería una tontería.
    """
    import unicodedata

    texto = unicodedata.normalize("NFKD", (respuesta or "").strip().lower())
    sin_tildes = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(sin_tildes.split())


def _usuario(fila) -> Usuario:
    claves = fila.keys()
    return Usuario(correo=fila["correo"], nombre=fila["nombre"], rol=fila["rol"],
                   activo=bool(fila["activo"]), creado=fila["creado"],
                   comision_pct=int(fila["comision_pct"]) if "comision_pct" in claves else -1,
                   verificado=bool(fila["verificado"]) if "verificado" in claves else True,
                   foto=(fila["foto"] if "foto" in claves else "") or "")


class Usuarios:
    def __init__(self, almacen: Almacen, horas_sesion: int = 12,
                 max_intentos: int = 5, minutos_bloqueo: int = 15) -> None:
        self.almacen = almacen
        self.horas_sesion = horas_sesion
        self.max_intentos = max_intentos
        self.minutos_bloqueo = minutos_bloqueo
        self._intentos: dict[str, tuple[int, float]] = {}

    # -- registro --

    def registrar(self, correo: str, clave: str, nombre: str = "", rol: str = "jugador",
                  pregunta: str = "", respuesta: str = "",
                  verificado: bool = True, codigo_amigo: str = "",
                  codigo_invitacion: str = "") -> Usuario:
        correo = (correo or "").strip().lower()
        if not CORREO_VALIDO.match(correo):
            raise ErrorDeUsuario("Ese correo no tiene buena pinta.")
        if self.almacen.usuario(correo):
            raise ErrorDeUsuario("Ya hay una cuenta con ese correo.")
        validar_clave(clave)
        if rol not in ("jugador", "admin"):
            raise ErrorDeUsuario("Rol no válido.")
        if pregunta:
            if pregunta not in PREGUNTAS:
                raise ErrorDeUsuario("Esa pregunta no es de la lista.")
            if len((respuesta or "").strip()) < 3:
                raise ErrorDeUsuario("La respuesta secreta es demasiado corta.")
        # Quién lo trajo. Se resuelve ahora y se guarda el correo, no el código:
        # así el padrino no cambia aunque el invitado use otro código después.
        padrino = ""
        codigo_amigo = (codigo_amigo or "").strip().upper()
        if codigo_amigo:
            fila_padrino = self.almacen.usuario_por_codigo(codigo_amigo)
            if fila_padrino is None:
                raise ErrorDeUsuario("Ese código de amigo no existe.")
            padrino = fila_padrino["correo"]
        # Quién lo trajo a la sala de trabajo. Es OTRO código (el de invitación),
        # no el de amigo: no dispara comisiones de referidos, solo dice de quién es
        # la gente que entra a trabajar desde casa.
        invitado_por = ""
        codigo_invitacion = (codigo_invitacion or "").strip().upper()
        if codigo_invitacion:
            fila_invita = self.almacen.usuario_por_invitacion(codigo_invitacion)
            if fila_invita is None:
                raise ErrorDeUsuario("Ese código de invitación no existe.")
            invitado_por = fila_invita["correo"]
        # El código propio se genera aquí y se garantiza único.
        mi_codigo = self._codigo_libre(correo)
        mi_codigo_casa = self._codigo_invitacion_libre(correo)
        self.almacen.crear_usuario(
            correo, hash_clave(clave), (nombre or "").strip(), rol, time.time(),
            pregunta, hash_clave(_normalizar_respuesta(respuesta)) if pregunta else "",
            verificado=verificado, codigo_amigo=mi_codigo, referido_por=padrino,
        )
        self.almacen.fijar_codigo_invitacion(correo, mi_codigo_casa, invitado_por)
        return Usuario(correo=correo, nombre=(nombre or "").strip(), rol=rol, activo=True,
                       creado=time.time(), verificado=verificado)

    def _codigo_libre(self, correo: str) -> str:
        """Un código de amigo corto y único, sacado del nombre o del correo."""
        base = re.sub(r"[^A-Z0-9]", "", (correo.split("@")[0] or "").upper())[:6]
        base = base or "AMIGO"
        for intento in range(20):
            sufijo = "" if intento == 0 else f"{secrets.randbelow(90) + 10}"
            codigo = f"{base}{sufijo}"[:10]
            if self.almacen.usuario_por_codigo(codigo) is None:
                return codigo
        return f"BINGO{secrets.token_hex(3).upper()}"

    def asegurar_codigo_amigo(self, correo: str) -> str:
        """Devuelve el código de amigo de una cuenta, generándolo si le falta.

        Hace falta para las cuentas creadas antes de que existieran los referidos
        (y para la de administración, que se crea por otro camino): sin esto su
        pantalla de referidos saldría en blanco.
        """
        correo = (correo or "").strip().lower()
        fila = self.almacen.usuario(correo)
        if fila is None:
            return ""
        claves = fila.keys()
        actual = (fila["codigo_amigo"] if "codigo_amigo" in claves else "") or ""
        if actual:
            return actual
        codigo = self._codigo_libre(correo)
        self.almacen.fijar_codigo_amigo(correo, codigo)
        return codigo

    def _codigo_invitacion_libre(self, correo: str) -> str:
        """Un código de invitación a la sala de trabajo, corto y único.

        Es distinto del código de amigo a propósito: el de amigo dispara las
        comisiones de referidos y este solo sirve para la sala de trabajo.
        """
        base = re.sub(r"[^A-Z0-9]", "", (correo.split("@")[0] or "").upper())[:6]
        base = base or "CASA"
        for intento in range(30):
            sufijo = "" if intento == 0 else f"{secrets.randbelow(900) + 100}"
            codigo = f"CASA{base}{sufijo}"[:12]
            if self.almacen.usuario_por_invitacion(codigo) is None:
                return codigo
        return f"CASA{secrets.token_hex(3).upper()}"

    def asegurar_codigo_invitacion(self, correo: str) -> str:
        """Devuelve el código de invitación a la sala de trabajo de una cuenta.

        Se genera la primera vez que hace falta. Todas las cuentas lo tienen
        (también la de administración), porque cualquiera puede invitar gente a la
        sala de trabajo.
        """
        correo = (correo or "").strip().lower()
        fila = self.almacen.usuario(correo)
        if fila is None:
            return ""
        claves = fila.keys()
        actual = (fila["codigo_invitacion"] if "codigo_invitacion" in claves else "") or ""
        if actual:
            return actual
        codigo = self._codigo_invitacion_libre(correo)
        self.almacen.fijar_codigo_invitacion(correo, codigo)
        return codigo

    def quien_invito(self, correo: str) -> str:
        """El correo de quien trajo a esta cuenta a la sala de trabajo ('' si no)."""
        correo = (correo or "").strip().lower()
        fila = self.almacen.usuario(correo)
        if fila is None or "invitado_por" not in fila.keys():
            return ""
        return fila["invitado_por"] or ""

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
        """Cambia la contraseña y CIERRA todas las sesiones de esa cuenta.

        Es lo importante: si alguien te había robado la cuenta, cambiar la clave
        sin cerrar sesiones no lo echa. Con esto, sí.
        """
        correo = correo.strip().lower()
        validar_clave(nueva)
        self.almacen.cambiar_huella(correo, hash_clave(nueva))
        self.almacen.borrar_sesiones_de(correo)

    def restablecer_por_admin(self, correo: str, nueva: str) -> None:
        """El administrador pone una contraseña nueva. Se cierran las sesiones."""
        self.cambiar_clave(correo, nueva)

    def cambiar_foto(self, correo: str, foto: str) -> str:
        """Guarda la foto de perfil de una cuenta. Devuelve la foto guardada."""
        correo = (correo or "").strip().lower()
        if not self.almacen.usuario(correo):
            raise ErrorDeUsuario("Esa cuenta no existe.")
        limpia = validar_foto(foto)
        self.almacen.cambiar_foto(correo, limpia)
        return limpia

    def foto_de(self, correo: str) -> str:
        return self.almacen.foto_de(correo)

    # -- recuperación: pregunta secreta --

    def pregunta_de(self, correo: str) -> str | None:
        fila = self.almacen.usuario((correo or "").strip().lower())
        return (fila["pregunta"] or None) if fila else None

    def verificar_respuesta(self, correo: str, respuesta: str) -> bool:
        fila = self.almacen.usuario((correo or "").strip().lower())
        if fila is None or not fila["respuesta_huella"]:
            return False
        return verificar_clave(_normalizar_respuesta(respuesta), fila["respuesta_huella"])

    def cambiar_con_respuesta(self, correo: str, respuesta: str, nueva: str) -> None:
        if not self.verificar_respuesta(correo, respuesta):
            raise ErrorDeUsuario("La respuesta no es correcta.")
        self.cambiar_clave(correo, nueva)

    # -- recuperación: código por correo --

    def pedir_codigo(self, correo: str, minutos: int = MINUTOS_CODIGO,
                     max_por_hora: int = CODIGOS_POR_HORA) -> str:
        """Genera un código de 6 cifras y devuelve el código en claro.

        Devuelve el código para que quien llama lo mande por correo. Nunca se
        guarda en claro: en la base solo queda su huella.

        Si el correo no existe, devuelve una cadena vacía en vez de fallar: así
        nadie puede usar esta pantalla para averiguar qué correos están dados de
        alta. Quien llama debe responder siempre lo mismo.
        """
        correo = (correo or "").strip().lower()
        if not CORREO_VALIDO.match(correo):
            raise ErrorDeUsuario("Ese correo no tiene buena pinta.")
        if not self.almacen.usuario(correo):
            return ""
        if self.almacen.codigos_recientes(correo, time.time() - 3600) >= max_por_hora:
            raise ErrorDeUsuario("Has pedido demasiados códigos. Espera una hora.")
        codigo = f"{secrets.randbelow(1_000_000):06d}"
        ahora = time.time()
        self.almacen.guardar_codigo(f"c-{secrets.token_hex(6)}", correo, hash_clave(codigo),
                                    ahora, ahora + minutos * 60)
        return codigo

    def cambiar_con_codigo(self, correo: str, codigo: str, nueva: str) -> None:
        correo = (correo or "").strip().lower()
        fila = self.almacen.codigo_pendiente(correo)
        if fila is None:
            raise ErrorDeUsuario("Pide un código nuevo.")
        if fila["caduca"] < time.time():
            self.almacen.usar_codigo(fila["id"])
            raise ErrorDeUsuario("Ese código ha caducado. Pide otro.")
        if not verificar_clave((codigo or "").strip(), fila["huella"]):
            intentos = self.almacen.fallar_codigo(fila["id"])
            restantes = max(0, INTENTOS_CODIGO - intentos)
            if restantes == 0:
                raise ErrorDeUsuario("Demasiados intentos. Pide un código nuevo.")
            raise ErrorDeUsuario(f"Código incorrecto. Te quedan {restantes} intentos.")
        validar_clave(nueva)
        self.almacen.usar_codigo(fila["id"])
        self.cambiar_clave(correo, nueva)

    def activar(self, correo: str, activo: bool) -> None:
        self.almacen.cambiar_activo(correo.strip().lower(), activo)

    # -- verificación del correo --

    def esta_verificado(self, correo: str) -> bool:
        u = self.usuario(correo)
        return bool(u and u.verificado)

    def marcar_verificado(self, correo: str) -> None:
        self.almacen.marcar_verificado((correo or "").strip().lower(), True)

    def pedir_codigo_verificacion(self, correo: str, minutos: int = MINUTOS_CODIGO,
                                  max_por_hora: int = CODIGOS_POR_HORA) -> str:
        """Genera un código para confirmar el correo de una cuenta recién creada.

        Se guarda aparte de los de recuperación (tipo 'verificacion'), para que
        pedir uno no anule el otro.
        """
        correo = (correo or "").strip().lower()
        if not CORREO_VALIDO.match(correo):
            raise ErrorDeUsuario("Ese correo no tiene buena pinta.")
        if not self.almacen.usuario(correo):
            return ""
        if self.almacen.codigos_recientes(correo, time.time() - 3600, "verificacion") >= max_por_hora:
            raise ErrorDeUsuario("Has pedido demasiados códigos. Espera una hora.")
        codigo = f"{secrets.randbelow(1_000_000):06d}"
        ahora = time.time()
        self.almacen.guardar_codigo(f"c-{secrets.token_hex(6)}", correo, hash_clave(codigo),
                                    ahora, ahora + minutos * 60, tipo="verificacion")
        return codigo

    def confirmar_correo(self, correo: str, codigo: str) -> None:
        """Marca la cuenta como verificada si el código es correcto."""
        correo = (correo or "").strip().lower()
        fila = self.almacen.codigo_pendiente(correo, "verificacion")
        if fila is None:
            raise ErrorDeUsuario("Pide un código nuevo.")
        if fila["caduca"] < time.time():
            self.almacen.usar_codigo(fila["id"])
            raise ErrorDeUsuario("Ese código ha caducado. Pide otro.")
        if not verificar_clave((codigo or "").strip(), fila["huella"]):
            intentos = self.almacen.fallar_codigo(fila["id"])
            restantes = max(0, INTENTOS_CODIGO - intentos)
            if restantes == 0:
                raise ErrorDeUsuario("Demasiados intentos. Pide un código nuevo.")
            raise ErrorDeUsuario(f"Código incorrecto. Te quedan {restantes} intentos.")
        self.almacen.usar_codigo(fila["id"])
        self.almacen.marcar_verificado(correo, True)

    def comision_de(self, correo: str, por_defecto: int) -> int:
        """El % de comisión de anfitrión de una cuenta (el fijo si no tiene propio)."""
        u = self.usuario(correo)
        if u is None or u.comision_pct < 0:
            return por_defecto
        return u.comision_pct

    def fijar_comision(self, correo: str, pct: int) -> None:
        """Fija el % de comisión de anfitrión de una cuenta. -1 vuelve al de defecto."""
        correo = (correo or "").strip().lower()
        if not self.almacen.usuario(correo):
            raise ErrorDeUsuario("No existe esa cuenta.")
        if not isinstance(pct, int) or isinstance(pct, bool) or not -1 <= pct <= 90:
            raise ErrorDeUsuario("El porcentaje tiene que estar entre 0 y 90 (o -1 para el fijo).")
        self.almacen.cambiar_comision(correo, pct)

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
        claves = fila.keys()
        if "verificado" in claves and not fila["verificado"]:
            raise ErrorDeUsuario("Confirma tu correo antes de entrar. Revisa tu bandeja.")
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
