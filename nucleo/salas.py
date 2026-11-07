"""Salas de bingo y reparto del dinero.

Aquí se decide, y se puede comprobar, en qué se convierte cada cartón vendido.
Es la parte más delicada del programa: si esto está mal, el dinero no cuadra.

El reparto, calcado del modelo de Juegoactivo:

    bote = precio del cartón x cartones vendidos

    premio al ganador  = 80 % del bote
    se queda la app    = 20 % del bote

Y cuando la sala es de un jugador (salas personalizadas, como en Juegoactivo),
el ganador cobra lo mismo y el 10 % del anfitrión sale del margen de la app:

    premio al ganador      = 80 % del bote   (igual que en las salas de la casa)
    comisión del anfitrión = 10 % del bote   (lo cobra quien creó la sala)
    se queda la app        = 10 % del bote

Así el anfitrión tiene motivo para traer jugadores, el jugador no cobra menos
por jugar en una sala de un particular, y la app nunca pierde dinero.

Todo va en céntimos enteros y el reparto se calcula de una vez, con el resto
asignado explícitamente. Nunca se pierde un céntimo por redondeo: la suma de
las tres partes es exactamente el bote.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from decimal import Decimal

from .money import a_centimos, a_texto


class ErrorDeSalas(ValueError):
    """La sala no se puede crear o no se puede usar."""


# Qué parte del bote va al ganador en cada tipo de sala.
PREMIO_CASA = Decimal("0.80")        # sala de la casa: 80 % al ganador
PREMIO_CON_ANFITRION = Decimal("0.80")  # sala de un jugador: el ganador cobra igual
COMISION_ANFITRION = Decimal("0.10")    # el anfitrión cobra un 10 % (sale del margen)

# Límites del precio del cartón, en céntimos. Ni regalado ni abusivo.
PRECIO_MINIMO = 1_00        # Bs 1,00
PRECIO_MAXIMO = 500_00      # Bs 500,00

MODOS_VALIDOS = ("normal", "carton_lleno", "competencia")

NOMBRES_RESERVADOS = ("dubai", "roma", "estelar")


def reparto_del_bote(bote: int, con_anfitrion: bool) -> dict:
    """Parte el bote en premio, comisión del anfitrión y lo que queda a la app.

    El resto del redondeo se le da al ganador, nunca a la casa: si sobra un
    céntimo, es del jugador. Así la app nunca gana por un error de redondeo.
    """
    if not isinstance(bote, int) or bote < 0:
        raise ErrorDeSalas(f"El bote tiene que ser un entero de céntimos, no {bote!r}.")

    proporcion = PREMIO_CON_ANFITRION if con_anfitrion else PREMIO_CASA
    premio = int((Decimal(bote) * proporcion).quantize(Decimal("1")))
    anfitrion = int((Decimal(bote) * COMISION_ANFITRION).quantize(Decimal("1"))) if con_anfitrion else 0
    # Lo que queda a la app es el bote menos lo repartido: por construcción, cuadra.
    app = bote - premio - anfitrion
    return {
        "bote": bote,
        "premio": premio,
        "anfitrion": anfitrion,
        "app": app,
        "con_anfitrion": con_anfitrion,
    }


@dataclass
class Sala:
    """Una sala de bingo. Define el modo, el precio y quién se lleva la comisión."""

    id: str
    nombre: str
    modo: str
    precio_carton: int                 # céntimos
    dueno: str = ""                    # correo del anfitrión; vacío = sala de la casa
    publica: bool = True
    creada: float = 0.0
    activa: bool = True

    @property
    def es_de_jugador(self) -> bool:
        return bool(self.dueno)

    @property
    def comision_anfitrion(self) -> int:
        """Céntimos que cobra el anfitrión por cada 100 de bote."""
        return int(COMISION_ANFITRION * 100) if self.es_de_jugador else 0

    def reparto(self, bote: int) -> dict:
        return reparto_del_bote(bote, con_anfitrion=self.es_de_jugador)

    def a_dict(self) -> dict:
        return {
            "id": self.id,
            "nombre": self.nombre,
            "modo": self.modo,
            "precio_carton": self.precio_carton,
            "precio_texto": a_texto(self.precio_carton),
            "dueno": self.dueno,
            "publica": self.publica,
            "activa": self.activa,
            "comision_anfitrion": self.comision_anfitrion,
            "es_de_jugador": self.es_de_jugador,
        }


# Las tres salas de la casa, como las de Juegoactivo (Dubai, Roma y Estelar).
SALAS_INICIALES = (
    ("sala-dubai", "Dubai", "normal", 5_00),
    ("sala-roma", "Roma", "competencia", 10_00),
    ("sala-estelar", "Estelar", "carton_lleno", 20_00),
)


class Salas:
    """Gestiona las salas: las de la casa y las que crean los jugadores."""

    def __init__(self, almacen) -> None:
        self.almacen = almacen
        self._asegurar_iniciales()

    def _asegurar_iniciales(self) -> None:
        """Crea las salas de la casa la primera vez. No pisa las que ya existan."""
        for id_, nombre, modo, precio in SALAS_INICIALES:
            if self.almacen.sala(id_) is None:
                self.almacen.guardar_sala({
                    "id": id_, "nombre": nombre, "modo": modo, "precio_carton": precio,
                    "dueno": "", "publica": 1, "creada": time.time(), "activa": 1,
                })

    # -- consulta --

    def todas(self, incluir_inactivas: bool = False) -> list[Sala]:
        return [self._a_sala(f) for f in self.almacen.salas(incluir_inactivas)]

    def publicas(self) -> list[Sala]:
        return [s for s in self.todas() if s.publica]

    def de(self, id_: str) -> Sala:
        fila = self.almacen.sala(id_)
        if fila is None:
            raise ErrorDeSalas(f"No existe la sala {id_!r}.")
        return self._a_sala(fila)

    def de_dueno(self, correo: str) -> list[Sala]:
        return [s for s in self.todas() if s.dueno == correo]

    # -- creación --

    def crear(self, dueno: str, nombre: str, modo: str, precio: object,
              publica: bool = True) -> Sala:
        """Un jugador crea su sala. El anfitrión se lleva el 10 % de los botes."""
        nombre = (nombre or "").strip()
        if not dueno:
            raise ErrorDeSalas("Hace falta saber quién crea la sala.")
        if not nombre:
            raise ErrorDeSalas("Ponle un nombre a la sala.")
        if len(nombre) > 30:
            raise ErrorDeSalas("El nombre de la sala no puede pasar de 30 letras.")
        if nombre.lower() in NOMBRES_RESERVADOS:
            raise ErrorDeSalas(f"El nombre {nombre!r} está reservado para las salas de la casa.")
        if modo not in MODOS_VALIDOS:
            raise ErrorDeSalas(f"Modo de juego no válido: {modo!r}.")
        centimos = a_centimos(precio)
        if not PRECIO_MINIMO <= centimos <= PRECIO_MAXIMO:
            raise ErrorDeSalas(
                f"El cartón tiene que costar entre {a_texto(PRECIO_MINIMO)} "
                f"y {a_texto(PRECIO_MAXIMO)}."
            )
        # Un anfitrión no puede llenar la web de salas.
        if len(self.de_dueno(dueno)) >= 3:
            raise ErrorDeSalas("Ya tienes 3 salas. Borra una para crear otra.")

        sala = Sala(id=f"s-{secrets.token_hex(4)}", nombre=nombre, modo=modo,
                    precio_carton=centimos, dueno=dueno, publica=bool(publica),
                    creada=time.time())
        self.almacen.guardar_sala({
            "id": sala.id, "nombre": sala.nombre, "modo": sala.modo,
            "precio_carton": sala.precio_carton, "dueno": sala.dueno,
            "publica": int(sala.publica), "creada": sala.creada, "activa": 1,
        })
        return sala

    def cerrar(self, id_: str, quien: str, es_admin: bool = False) -> Sala:
        """Cierra una sala. Solo su dueño o la administración."""
        sala = self.de(id_)
        if not es_admin and sala.dueno != quien:
            raise ErrorDeSalas("Esa sala no es tuya.")
        self.almacen.activar_sala(id_, False)
        return self.de(id_)

    # -- ganancias --

    def ganancias(self, correo: str) -> dict:
        """Lo que ha ganado un anfitrión con sus salas, y lo que ha dejado a la app."""
        salas = self.de_dueno(correo)
        ids = {s.id for s in salas}
        total_anfitrion = 0
        total_app = 0
        total_botes = 0
        partidas = 0
        for fila in self.almacen.partidas(1000):
            if fila["sala"] not in ids or fila["estado"] != "terminada":
                continue
            bote = fila["precio_carton"] * len(self.almacen.cartones(fila["id"]))
            if bote == 0:
                continue
            r = reparto_del_bote(bote, con_anfitrion=True)
            total_anfitrion += r["anfitrion"]
            total_app += r["app"]
            total_botes += bote
            partidas += 1
        return {
            "correo": correo,
            "salas": len(salas),
            "partidas": partidas,
            "botes": total_botes,
            "botes_texto": a_texto(total_botes),
            "anfitrion": total_anfitrion,
            "anfitrion_texto": a_texto(total_anfitrion),
            "app": total_app,
            "app_texto": a_texto(total_app),
        }

    def economia(self) -> dict:
        """Resumen para el panel: cuánto ha movido el bingo y cuánto queda a la app."""
        partidas = 0
        botes = 0
        premios = 0
        comisiones = 0
        app = 0
        for fila in self.almacen.partidas(1000):
            if fila["estado"] != "terminada":
                continue
            bote = fila["precio_carton"] * len(self.almacen.cartones(fila["id"]))
            if bote == 0:
                continue
            con_anf = bool(fila["sala"] and self._es_de_jugador(fila["sala"]))
            r = reparto_del_bote(bote, con_anfitrion=con_anf)
            botes += r["bote"]
            premios += r["premio"]
            comisiones += r["anfitrion"]
            app += r["app"]
            partidas += 1
        return {
            "partidas": partidas,
            "botes": botes, "botes_texto": a_texto(botes),
            "premios": premios, "premios_texto": a_texto(premios),
            "comisiones": comisiones, "comisiones_texto": a_texto(comisiones),
            "app": app, "app_texto": a_texto(app),
        }

    def _es_de_jugador(self, sala_id: str) -> bool:
        fila = self.almacen.sala(sala_id)
        return bool(fila and fila["dueno"])

    def _a_sala(self, fila) -> Sala:
        return Sala(id=fila["id"], nombre=fila["nombre"], modo=fila["modo"],
                    precio_carton=fila["precio_carton"], dueno=fila["dueno"],
                    publica=bool(fila["publica"]), creada=fila["creada"],
                    activa=bool(fila["activa"]))
