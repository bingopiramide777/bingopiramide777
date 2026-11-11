"""Salas de bingo y reparto del dinero.

Aquí se decide, y se puede comprobar, en qué se convierte cada cartón vendido.
Es la parte más delicada del programa: si esto está mal, el dinero no cuadra.

El reparto:

    bote = precio del cartón x cartones vendidos

Hay tres clases de sala, y en cada una el bote se parte así:

    sala de la casa:      ganador 80 %  ·  app 20 %
    sala de un jugador:   ganador 70 %  ·  anfitrión 10 %  ·  app 20 %
    sala de trabajo:      ganador 80 %  ·  anfitrión 15 %  ·  app 5 %

Las **salas de la casa** (los estados) dejan todo su margen a la app. Las
**salas de un jugador** son las que puede crear cualquiera: el ganador cobra un
poco menos porque parte del bote va al anfitrión que organiza. La **sala de
trabajo** (la de "Ganar Dinero Desde Casa") premia más al anfitrión que trae a
los jugadores y baja la parte de la app.

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
from .paises import PAIS_POR_DEFECTO, cuenta_admin, formatear_local


class ErrorDeSalas(ValueError):
    """La sala no se puede crear o no se puede usar."""


# Qué parte del bote va al ganador en cada tipo de sala.
PREMIO_CASA = Decimal("0.80")            # sala de la casa: 80 % al ganador (app 20 %)
PREMIO_CON_ANFITRION = Decimal("0.70")   # sala de un jugador: 70 % al ganador

# Reparto por defecto de una sala que reparte TRES puestos (1º, 2º y 3º). Suma el
# 70 % que se llevaba el ganador único, así que deja intacta la parte del
# anfitrión (10 %) y la de la app (20 %).
PREMIO_JUGADOR_TRES_PUESTOS = (50, 15, 5)
# Cuántos puestos puede repartir una sala: uno (ganador único) o tres.
PUESTOS_VALIDOS = (1, len(PREMIO_JUGADOR_TRES_PUESTOS))
# Sala normal de un anfitrión: el 30 % que no va al ganador se parte 10 % para el
# anfitrión y 20 % para la app (que ya cobró su 20 % anticipado al acreditar el
# depósito: por eso no le toca nada más del bote).
COMISION_ANFITRION = Decimal("0.10")    # comisión por defecto del anfitrión
# Sala de trabajo ("Ganar Dinero Desde Casa"): el ganador cobra como en una sala
# de la casa (80 %) y el 20 % restante se parte 15 % para el anfitrión y 5 % para
# la app, porque es él quien trae a los jugadores.
COMISION_TRABAJO = Decimal("0.15")
PREMIO_TRABAJO = Decimal("0.80")

# Límites del precio del cartón, en céntimos. Ni regalado ni abusivo.
# Las salas de la casa y el evento los pone la administración desde el panel, así
# que su tope es más alto que el de las salas de jugador.
PRECIO_MINIMO = 1_00        # $ 1,00
PRECIO_MAXIMO = 500_00      # $ 500,00 (salas de jugador)
PRECIO_MAXIMO_CASA = 100_000_00  # $ 100.000,00 (salas de la casa y el evento)

MODOS_VALIDOS = ("normal", "carton_lleno", "competencia")

# Tipos de juego (patrón que premia la sala). Los pone la administración.
TIPO_JUEGO_POR_DEFECTO = "linea_h1"
CUPO_MAXIMO_CARTONES = 1000        # cartones que se pueden vender en una sala (0 = sin tope)

# Cuántos cartones puede comprar un mismo jugador en una sala (0 = sin tope).
# Es distinto del cupo: el cupo limita la sala entera, esto limita a cada quien.
MAX_CARTONES_POR_JUGADOR = 100

# Las salas de jugador llevan nombres cortos (30 letras). Las de la casa y el
# evento admiten nombres largos, como el de la sala de jugar desde casa.
NOMBRE_MAXIMO_JUGADOR = 30
NOMBRE_MAXIMO_CASA = 60

# Las salas de la casa llevan nombre de estado de Venezuela. El último dato es
# el tipo de juego que premia la sala. El precio es en dólares (céntimos).
SALAS_INICIALES = (
    ("sala-zulia", "Zulia", "carton_lleno", 10_00, "carton_lleno", "VE"),
    ("sala-lara", "Lara", "carton_lleno", 5_00, "carton_lleno", "VE"),
    ("sala-carabobo", "Carabobo", "carton_lleno", 3_00, "carton_lleno", "VE"),
    ("sala-miranda", "Mérida", "normal", 2_00, "cruz_grande", "VE"),
    ("sala-tachira", "Táchira", "competencia", 1_00, "cruz_pequena", "VE"),
    ("sala-nueva-esparta", "Nueva Esparta", "carton_lleno", 1_00, "diagonal", "VE"),
)

# La sala para jugar desde casa. Es una sala de la casa (no de un anfitrión),
# de cartón lleno y con tope de 6 cartones por jugador para que el bote se
# reparta entre más gente. El precio lo cambia la administración desde el panel.
SALA_CASA_ID = "sala-ganar-desde-casa"
SALA_CASA_NOMBRE = "Ganar Dinero Desde Casa con BingoPiramide777"
SALA_CASA_MODO = "carton_lleno"
SALA_CASA_PRECIO = 2_00           # $ 2,00 por cartón
SALA_CASA_TIPO = "carton_lleno"
SALA_CASA_MAX_CARTONES = 6         # cartones por jugador

# Precios que traían las salas antes del cambio a dólares (en céntimos de
# bolívar). Se usan una sola vez, para convertir la base de datos de quien ya
# tenía el programa funcionando. Si un precio no coincide con el viejo, es que lo
# cambió la administración y no se toca.
SALAS_INICIALES_ANTIGUAS = {
    "sala-zulia": 2_000_00,
    "sala-lara": 1_000_00,
    "sala-carabobo": 500_00,
    "sala-miranda": 200_00,
    "sala-tachira": 100_00,
    "sala-nueva-esparta": 50_00,
}

# El precio en bolívares que traía la sala de jugar desde casa.
SALA_CASA_PRECIO_ANTIGUO = 50_00

# Nombre viejo de la sala de Mérida, cuando era "Miranda".
NOMBRE_VIEJO_MIRANDA = "Miranda"

# Marca de "los precios nuevos ya se aplicaron". Sube solo si hay que volver a
# tocar los precios de las bases ya existentes. La 2 es el cambio a dólares.
VERSION_PRECIOS = 2

# Marca de "los juegos nuevos ya se aplicaron". La 1 es el paso de Zulia y Lara
# a cartón lleno. Solo se toca una sala si todavía tiene su juego viejo.
VERSION_JUEGOS = 1

# Marca de "la sala de trabajo ya se aplicó". La 1 pone dueño y modo de trabajo a
# "Ganar Dinero Desde Casa" una sola vez.
VERSION_TRABAJO = 1
# El juego viejo de Zulia y Lara, antes de pasarlas a cartón lleno.
JUEGOS_ANTIGUOS = {
    "sala-zulia": ("normal", "linea_h1"),
    "sala-lara": ("competencia", "cuatro_esquinas"),
}

# Sala de eventos: la maneja la administración. Ella pone el aforo, el precio del
# cartón y el porcentaje del bote que se lleva cada puesto.
SALA_EVENTO_ID = "sala-evento-lago"
SALA_EVENTO_NOMBRE = "Sala de Eventos Lago de Maracaibo"
SALA_EVENTO_MODO = "competencia"
SALA_EVENTO_TIPO = "cruz_grande"           # tipo de juego por defecto del evento
SALA_EVENTO_PRECIO = 2_00                 # $ 2,00 por cartón
SALA_EVENTO_AFORO = 50                     # jugadores como máximo (0 = sin límite)
SALA_EVENTO_CUPO = 0                       # cartones como máximo (0 = sin tope)
PREMIO_EVENTO_POR_DEFECTO = (60, 15, 5)    # % del bote para 1º, 2º y 3º
PLAZAS_EVENTO = len(PREMIO_EVENTO_POR_DEFECTO)
AFORO_MAXIMO = 1000

NOMBRES_RESERVADOS = tuple(n.lower() for _, n, _, _, _, _ in SALAS_INICIALES) + (
    NOMBRE_VIEJO_MIRANDA.lower(), SALA_EVENTO_NOMBRE.lower(), "lago de maracaibo",
    SALA_CASA_NOMBRE.lower(),
)


def reparto_del_bote(bote: int, con_anfitrion: bool, comision_pct: int | None = None,
                     premio_pct: Decimal | None = None) -> dict:
    """Parte el bote en premio, comisión del anfitrión y lo que queda a la app.

    El resto del redondeo se le da al ganador, nunca a la casa: si sobra un
    céntimo, es del jugador. Así la app nunca gana por un error de redondeo.
    La comisión del anfitrión se puede ajustar por cuenta (comision_pct, en %);
    si no se pasa, se usa la de por defecto. El premio del ganador también se
    puede ajustar (premio_pct): las salas de jugador dan el 70 % y las de trabajo
    el 80 %.
    """
    if not isinstance(bote, int) or bote < 0:
        raise ErrorDeSalas(f"El bote tiene que ser un entero de céntimos, no {bote!r}.")

    pct = int(COMISION_ANFITRION * 100) if comision_pct is None else comision_pct
    if not isinstance(pct, int) or isinstance(pct, bool) or not 0 <= pct <= 100:
        raise ErrorDeSalas(f"Porcentaje de anfitrión no válido: {pct!r}.")

    proporcion = premio_pct if premio_pct is not None else (
        PREMIO_CON_ANFITRION if con_anfitrion else PREMIO_CASA)
    premio = int((Decimal(bote) * Decimal(proporcion)).quantize(Decimal("1")))
    anfitrion = int((Decimal(bote) * Decimal(pct) / 100).quantize(Decimal("1"))) if con_anfitrion else 0
    # Lo que queda a la app es el bote menos lo repartido: por construcción, cuadra.
    app = bote - premio - anfitrion
    return {
        "bote": bote,
        "premio": premio,
        "anfitrion": anfitrion,
        "app": app,
        "con_anfitrion": con_anfitrion,
        "comision_pct": pct,
    }


def reparto_por_puestos(bote: int, porcentajes: tuple[int, ...] | list[int],
                        con_anfitrion: bool = False, comision_pct: int = 0) -> dict:
    """Parte el bote entre varios puestos, con la comisión del anfitrión opcional.

    Cada puesto cobra su porcentaje del bote, truncado al céntimo. El anfitrión
    cobra su comisión (si la sala tiene dueño) y lo que queda es de la app: la
    suma de los premios más la comisión más lo de la app es exactamente el bote.
    """
    if not isinstance(bote, int) or bote < 0:
        raise ErrorDeSalas(f"El bote tiene que ser un entero de céntimos, no {bote!r}.")
    if not porcentajes:
        raise ErrorDeSalas("Hace falta al menos un puesto premiado.")
    for pct in porcentajes:
        if not isinstance(pct, int) or isinstance(pct, bool) or pct < 0:
            raise ErrorDeSalas(f"Porcentaje no válido: {pct!r}.")
    if not isinstance(comision_pct, int) or isinstance(comision_pct, bool) \
            or not 0 <= comision_pct <= 100:
        raise ErrorDeSalas(f"Porcentaje de anfitrión no válido: {comision_pct!r}.")
    if sum(porcentajes) + (comision_pct if con_anfitrion else 0) > 100:
        raise ErrorDeSalas("Los porcentajes no pueden sumar más de 100 %.")
    premios = [bote * pct // 100 for pct in porcentajes]
    anfitrion = bote * comision_pct // 100 if con_anfitrion else 0
    return {"bote": bote, "premio": premios[0], "premios": premios,
            "anfitrion": anfitrion, "app": bote - sum(premios) - anfitrion,
            "con_anfitrion": con_anfitrion, "comision_pct": comision_pct,
            "porcentajes": list(porcentajes)}


def reparto_evento(bote: int, porcentajes: tuple[int, ...] | list[int]) -> dict:
    """Parte el bote de un evento entre los puestos, por porcentaje.

    Un evento no tiene anfitrión: cada puesto cobra su porcentaje del bote,
    truncado al céntimo, y lo que no se reparte queda para la app.
    """
    if not porcentajes:
        raise ErrorDeSalas("Un evento necesita al menos un puesto premiado.")
    r = reparto_por_puestos(bote, list(porcentajes))
    return {"bote": r["bote"], "premios": r["premios"], "app": r["app"],
            "porcentajes": r["porcentajes"]}


@dataclass
class Sala:
    """Una sala de bingo. Define el modo, el precio y quién se lleva la comisión.

    Las salas de evento (es_evento) las maneja la administración: llevan aforo de
    jugadores y reparten el bote por porcentaje entre varios puestos.
    """

    id: str
    nombre: str
    modo: str
    precio_carton: int                 # céntimos
    dueno: str = ""                    # correo del anfitrión; vacío = sala de la casa
    publica: bool = True
    creada: float = 0.0
    activa: bool = True
    es_evento: bool = False
    aforo: int = 0                     # jugadores como máximo; 0 = sin límite
    premios_pct: tuple[int, ...] = ()  # % del bote para 1º, 2º y 3º (solo eventos)
    tipo_juego: str = TIPO_JUEGO_POR_DEFECTO  # patrón que premia la sala
    cupo_cartones: int = 0             # cartones a la venta como máximo; 0 = sin tope
    max_cartones: int = 0              # cartones por jugador como máximo; 0 = sin tope
    fecha_partida: str = ""            # cuándo se juega (texto libre: "hoy 8 pm")
    pais: str = "VE"                   # país y moneda de la sala (Opción A)
    es_trabajo: bool = False           # sala de trabajo: el anfitrión pone juego y precio

    @property
    def es_de_jugador(self) -> bool:
        return bool(self.dueno)

    @property
    def precio_texto(self) -> str:
        """El precio del cartón en la moneda de QUIEN MIRA (se convierte)."""
        return a_texto(self.precio_carton)

    @property
    def precio_nativo_texto(self) -> str:
        """El precio del cartón en la moneda propia de la sala (sin convertir)."""
        from .paises import formatear_local

        return formatear_local(self.precio_carton, self.pais)

    @property
    def nombre_tipo_juego(self) -> str:
        from bingo.cartones import NOMBRE_TIPO_JUEGO
        return NOMBRE_TIPO_JUEGO.get(self.tipo_juego, self.tipo_juego)

    @property
    def comision_anfitrion(self) -> int:
        """Porcentaje del bote que cobra el anfitrión (0 si la sala es de la casa)."""
        if not self.es_de_jugador:
            return 0
        pct = COMISION_TRABAJO if self.es_trabajo else COMISION_ANFITRION
        return int(pct * 100)

    @property
    def premio_pct(self) -> Decimal:
        """Qué parte del bote se lleva el ganador único (el resto es anfitrión y app)."""
        if self.es_trabajo:
            return PREMIO_TRABAJO
        return PREMIO_CON_ANFITRION if self.es_de_jugador else PREMIO_CASA

    @property
    def reparte_varios_puestos(self) -> bool:
        """¿La sala reparte el bote entre varios puestos (1º, 2º, 3º)?"""
        return len(self.premios_pct) > 1

    @property
    def plazas(self) -> int:
        """Cuántos puestos premiados reparte la sala (uno si no reparte varios)."""
        return len(self.premios_pct) if self.premios_pct else 1

    def reparto(self, bote: int, comision_pct: int | None = None) -> dict:
        if comision_pct is None:
            # Sala de trabajo: 15 % para el anfitrión. Sala normal: 10 %.
            comision_pct = self.comision_anfitrion if self.es_de_jugador else 0
        if self.reparte_varios_puestos:
            return reparto_por_puestos(bote, self.premios_pct,
                                       con_anfitrion=self.es_de_jugador,
                                       comision_pct=comision_pct)
        if self.es_evento:
            return reparto_evento(bote, self.premios_pct)
        return reparto_del_bote(bote, con_anfitrion=self.es_de_jugador,
                                comision_pct=comision_pct, premio_pct=self.premio_pct)

    def a_dict(self) -> dict:
        return {
            "id": self.id,
            "nombre": self.nombre,
            "modo": self.modo,
            "precio_carton": self.precio_carton,
            "precio_texto": self.precio_texto,
            "pais": self.pais,
            "dueno": self.dueno,
            "publica": self.publica,
            "activa": self.activa,
            "comision_anfitrion": self.comision_anfitrion,
            "premio_pct": int(self.premio_pct * 100),
            "es_de_jugador": self.es_de_jugador,
            "es_evento": self.es_evento,
            "aforo": self.aforo,
            "premios_pct": list(self.premios_pct),
            "plazas": self.plazas,
            "reparte_varios_puestos": self.reparte_varios_puestos,
            "tipo_juego": self.tipo_juego,
            "tipo_juego_texto": self.nombre_tipo_juego,
            "cupo_cartones": self.cupo_cartones,
            "max_cartones": self.max_cartones,
            "fecha_partida": self.fecha_partida,
            "es_trabajo": self.es_trabajo,
        }


class Salas:
    """Gestiona las salas: las de la casa y las que crean los jugadores."""

    def __init__(self, almacen, usuarios=None, anfitrion_casa: str = "") -> None:
        self.almacen = almacen
        self.usuarios = usuarios
        # Correo que hace de anfitrión en la sala de trabajo ("Ganar Dinero Desde
        # Casa"). Es la cuenta de administración: cobra el 15 % de esa sala.
        self.anfitrion_casa = anfitrion_casa
        self._asegurar_iniciales()
        self._subir_precios_antiguos()
        self._subir_juegos_antiguos()
        self._subir_sala_trabajo()

    def comision_de(self, dueno: str, defecto: int | None = None) -> int:
        """El % de comisión de anfitrión que le toca a una cuenta.

        Cada cuenta puede tener su propio porcentaje (lo pone la administración);
        si no lo tiene, se usa el de por defecto. El defecto cambia según la sala
        (15 % en las salas de trabajo, 10 % en las demás).
        """
        if defecto is None:
            defecto = int(COMISION_ANFITRION * 100)
        if not dueno or self.usuarios is None:
            return defecto
        return self.usuarios.comision_de(dueno, defecto)

    def _subir_precios_antiguos(self) -> None:
        """Pone los precios nuevos en bases de datos creadas antes.

        Solo toca una sala si su precio sigue siendo el viejo: así no se pisa un
        precio que la administración haya cambiado a mano. Se hace una sola vez.
        """
        if self.almacen.meta("precios_v") == str(VERSION_PRECIOS):
            return
        nuevos = {id_: precio for id_, _, _, precio, _, _ in SALAS_INICIALES}
        for id_, viejo in SALAS_INICIALES_ANTIGUAS.items():
            fila = self.almacen.sala(id_)
            if fila is None:
                continue
            campos = {}
            if fila["precio_carton"] == viejo and nuevos[id_] != viejo:
                campos["precio_carton"] = nuevos[id_]
            # La sala de Mérida se llamaba Miranda.
            if id_ == "sala-miranda" and fila["nombre"] == NOMBRE_VIEJO_MIRANDA:
                campos["nombre"] = "Mérida"
            if campos:
                self.almacen.actualizar_sala(id_, campos)
        # La sala de jugar desde casa y el evento también bajan de bolívares a
        # dólares, si siguen con el precio viejo.
        for id_, nuevo in ((SALA_CASA_ID, SALA_CASA_PRECIO),
                           (SALA_EVENTO_ID, SALA_EVENTO_PRECIO)):
            fila = self.almacen.sala(id_)
            if fila is None:
                continue
            if fila["precio_carton"] == SALA_CASA_PRECIO_ANTIGUO:
                self.almacen.actualizar_sala(id_, {"precio_carton": nuevo})
        self.almacen.guardar_meta("precios_v", str(VERSION_PRECIOS))

    def _subir_juegos_antiguos(self) -> None:
        """Pasa Zulia y Lara a cartón lleno en bases de datos creadas antes.

        Solo toca una sala si todavía tiene su juego viejo (modo y tipo), para no
        pisar un cambio que haya hecho la administración. Se hace una sola vez.
        """
        if self.almacen.meta("juegos_v") == str(VERSION_JUEGOS):
            return
        for id_, (modo_viejo, tipo_viejo) in JUEGOS_ANTIGUOS.items():
            fila = self.almacen.sala(id_)
            if fila is None:
                continue
            if fila["modo"] == modo_viejo and fila["tipo_juego"] == tipo_viejo:
                self.almacen.actualizar_sala(id_, {"modo": "carton_lleno",
                                                   "tipo_juego": "carton_lleno"})
        self.almacen.guardar_meta("juegos_v", str(VERSION_JUEGOS))

    def _subir_sala_trabajo(self) -> None:
        """Convierte "Ganar Dinero Desde Casa" en la sala de trabajo de la casa.

        Le pone dueño (la cuenta de administración) y la marca como sala de
        trabajo, para que su anfitrión cobre el 15 % y la app solo el 5 %. Se hace
        una sola vez; después la administración puede tocar el dueño desde el panel.
        """
        if not self.anfitrion_casa:
            return
        if self.almacen.meta("trabajo_v") == str(VERSION_TRABAJO):
            return
        fila = self.almacen.sala(SALA_CASA_ID)
        if fila is not None and not fila["dueno"]:
            self.almacen.actualizar_sala(SALA_CASA_ID, {"dueno": self.anfitrion_casa,
                                                        "es_trabajo": 1})
        self.almacen.guardar_meta("trabajo_v", str(VERSION_TRABAJO))

    def _asegurar_iniciales(self) -> None:
        """Crea las salas de la casa la primera vez. No pisa las que ya existan."""
        for id_, nombre, modo, precio, tipo, pais in SALAS_INICIALES:
            if self.almacen.sala(id_) is None:
                self.almacen.guardar_sala({
                    "id": id_, "nombre": nombre, "modo": modo, "precio_carton": precio,
                    "dueno": "", "publica": 1, "creada": time.time(), "activa": 1,
                    "es_evento": 0, "aforo": 0, "premios_pct": "", "tipo_juego": tipo,
                    "pais": pais,
                })
        if self.almacen.sala(SALA_CASA_ID) is None:
            self.almacen.guardar_sala({
                "id": SALA_CASA_ID, "nombre": SALA_CASA_NOMBRE, "modo": SALA_CASA_MODO,
                "precio_carton": SALA_CASA_PRECIO,
                "dueno": self.anfitrion_casa if self.anfitrion_casa else "",
                "publica": 1, "creada": time.time(), "activa": 1, "es_evento": 0,
                "tipo_juego": SALA_CASA_TIPO, "es_trabajo": 1 if self.anfitrion_casa else 0,
                "max_cartones": SALA_CASA_MAX_CARTONES,
            })
        if self.almacen.sala(SALA_EVENTO_ID) is None:
            self.almacen.guardar_sala({
                "id": SALA_EVENTO_ID, "nombre": SALA_EVENTO_NOMBRE, "modo": SALA_EVENTO_MODO,
                "precio_carton": SALA_EVENTO_PRECIO, "dueno": "", "publica": 1,
                "creada": time.time(), "activa": 1, "es_evento": 1,
                "aforo": SALA_EVENTO_AFORO,
                "premios_pct": ",".join(str(p) for p in PREMIO_EVENTO_POR_DEFECTO),
                "tipo_juego": SALA_EVENTO_TIPO,
            })

    # -- consulta --

    def todas(self, incluir_inactivas: bool = False) -> list[Sala]:
        return [self._a_sala(f) for f in self.almacen.salas(incluir_inactivas)]

    def de_la_casa(self, incluir_inactivas: bool = False) -> list[Sala]:
        """Las salas de los estados: sin la de eventos ni la de trabajo."""
        return [s for s in self.todas(incluir_inactivas)
                if not s.es_evento and not s.dueno and s.id != SALA_CASA_ID]

    def evento(self) -> Sala:
        """La sala de eventos Lago de Maracaibo."""
        return self.de(SALA_EVENTO_ID)

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
              publica: bool = True, pais: str | None = None,
              puestos: object = 1, premios_pct: object | None = None) -> Sala:
        """Un jugador crea su sala. El anfitrión se lleva el 10 % de los botes.

        Las salas de jugador reparten un puesto (el ganador cobra el 70 %, el
        anfitrión el 10 % y la app el 20 %) o tres (1º, 2º y 3º). Con varios
        puestos los porcentajes se pueden pasar a mano; si no, se usa el reparto
        por defecto (50/15/5, que deja la comisión y la app igual).

        La sala nace con un país (y por tanto una moneda). Si no se indica, se usa
        el país del jugador que la crea, y si tampoco, el de por defecto. El precio
        se entiende en ESA moneda.
        """
        nombre = (nombre or "").strip()
        if not dueno:
            raise ErrorDeSalas("Hace falta saber quién crea la sala.")
        if not nombre:
            raise ErrorDeSalas("Ponle un nombre a la sala.")
        if len(nombre) > NOMBRE_MAXIMO_JUGADOR:
            raise ErrorDeSalas(f"El nombre de la sala no puede pasar de {NOMBRE_MAXIMO_JUGADOR} letras.")
        if nombre.lower() in NOMBRES_RESERVADOS:
            raise ErrorDeSalas(f"El nombre {nombre!r} está reservado para las salas de la casa.")
        if modo not in MODOS_VALIDOS:
            raise ErrorDeSalas(f"Modo de juego no válido: {modo!r}.")
        from .paises import a_base, es_pais_valido

        pais = (pais or "").strip().upper()
        if not es_pais_valido(pais):
            pais = PAIS_POR_DEFECTO
        # El precio llega en la moneda del anfitrión; dentro se guarda en la base.
        centimos = a_base(a_centimos(precio), pais)
        if not PRECIO_MINIMO <= centimos <= PRECIO_MAXIMO:
            raise ErrorDeSalas(
                f"El cartón de tu sala tiene que costar entre {a_texto(PRECIO_MINIMO)} "
                f"y {a_texto(PRECIO_MAXIMO)}."
            )
        # Un anfitrión no puede llenar la web de salas.
        if len(self.de_dueno(dueno)) >= 3:
            raise ErrorDeSalas("Ya tienes 3 salas. Borra una para crear otra.")

        reparto_puestos = self._premios_de_puestos(puestos, premios_pct)
        sala = Sala(id=f"s-{secrets.token_hex(4)}", nombre=nombre, modo=modo,
                    precio_carton=centimos, dueno=dueno, publica=bool(publica),
                    creada=time.time(), pais=pais, premios_pct=reparto_puestos)
        self.almacen.guardar_sala({
            "id": sala.id, "nombre": sala.nombre, "modo": sala.modo,
            "precio_carton": sala.precio_carton, "dueno": sala.dueno,
            "publica": int(sala.publica), "creada": sala.creada, "activa": 1,
            "pais": sala.pais, "es_trabajo": int(sala.es_trabajo),
            "premios_pct": ",".join(str(p) for p in sala.premios_pct),
        })
        return sala

    def _premios_de_puestos(self, puestos: object, premios_pct: object | None) -> tuple[int, ...]:
        """Valida los puestos y los porcentajes de una sala.

        Devuelve la tupla de porcentajes: vacía para un solo ganador (el reparto de
        siempre) o los porcentajes de 1º, 2º y 3º. La comisión del anfitrión y lo
        de la app no van aquí: van aparte, así que los premios suman como máximo 70.
        """
        try:
            n = int(puestos)
        except (TypeError, ValueError):
            raise ErrorDeSalas("El número de puestos tiene que ser 1 o 3.") from None
        if n not in PUESTOS_VALIDOS:
            raise ErrorDeSalas("Una sala reparte 1 puesto (un ganador) o 3 (1º, 2º y 3º).")
        if premios_pct is None:
            if n == 1:
                return ()
            return tuple(PREMIO_JUGADOR_TRES_PUESTOS)
        if isinstance(premios_pct, str):
            trozos = [t for t in premios_pct.replace(" ", "").split(",") if t]
        else:
            trozos = list(premios_pct)
        try:
            porcentajes = tuple(int(t) for t in trozos)
        except (TypeError, ValueError):
            raise ErrorDeSalas("Los porcentajes tienen que ser números enteros.") from None
        if len(porcentajes) != n:
            raise ErrorDeSalas(f"Elegiste {n} puesto(s): hacen falta {n} porcentaje(s).")
        if any(p < 0 or p > 100 for p in porcentajes):
            raise ErrorDeSalas("Cada porcentaje tiene que estar entre 0 y 100.")
        # Los premios no pueden comerse la comisión del anfitrión (10 %) ni lo de
        # la app (20 %): entre todos, como mucho el 70 % del bote.
        if sum(porcentajes) > 70:
            raise ErrorDeSalas("Los premios no pueden pasar del 70 % del bote.")
        return porcentajes

    def comision_de_sala(self, sala_id: str) -> int:
        """El % de comisión que cobra el anfitrión de una sala (0 si no tiene dueño).

        En una sala de trabajo el anfitrión se lleva el 15 % por defecto (salvo
        que la administración le haya fijado otro porcentaje a su cuenta).
        """
        sala = self.de(sala_id)
        if not sala.es_de_jugador:
            return 0
        defecto = sala.comision_anfitrion
        return self.comision_de(sala.dueno, defecto)

    def reparto_de_sala(self, sala_id: str, bote: int) -> dict:
        """Parte el bote de una sala según su tipo (casa, jugador o trabajo).

        Es el único sitio donde se decide el reparto: lo usan el motor de bingo y
        el panel, para que todos vean siempre las mismas cuentas.
        """
        sala = self.de(sala_id)
        return sala.reparto(bote, self.comision_de_sala(sala_id))

    def cerrar(self, id_: str, quien: str, es_admin: bool = False) -> Sala:
        """Cierra una sala. Solo su dueño o la administración."""
        sala = self.de(id_)
        if not es_admin and sala.dueno != quien:
            raise ErrorDeSalas("Esa sala no es tuya.")
        self.almacen.activar_sala(id_, False)
        return self.de(id_)

    # -- configuración desde el panel (solo administración) --

    def _precio_valido(self, precio: object, tope: int, quien: str) -> int:
        centimos = a_centimos(precio)
        if not PRECIO_MINIMO <= centimos <= tope:
            raise ErrorDeSalas(
                f"El cartón {quien} tiene que costar entre {a_texto(PRECIO_MINIMO)} "
                f"y {a_texto(tope)}."
            )
        return centimos

    def _tipo_juego_valido(self, tipo: object) -> str:
        from bingo.cartones import PATRONES
        limpio = str(tipo or "").strip()
        if limpio not in PATRONES:
            raise ErrorDeSalas(f"Tipo de juego no válido: {limpio!r}.")
        return limpio

    def _cupo_valido(self, cupo: object) -> int:
        try:
            n = int(cupo)
        except (TypeError, ValueError):
            raise ErrorDeSalas("El cupo de cartones tiene que ser un número entero.") from None
        if n < 0 or n > CUPO_MAXIMO_CARTONES:
            raise ErrorDeSalas(f"El cupo tiene que estar entre 0 y {CUPO_MAXIMO_CARTONES} "
                               "(0 = sin tope).")
        return n

    def _max_cartones_valido(self, tope: object) -> int:
        try:
            n = int(tope)
        except (TypeError, ValueError):
            raise ErrorDeSalas("El tope de cartones por jugador tiene que ser un número entero.") from None
        if n < 0 or n > MAX_CARTONES_POR_JUGADOR:
            raise ErrorDeSalas(f"El tope de cartones por jugador tiene que estar entre 0 y "
                               f"{MAX_CARTONES_POR_JUGADOR} (0 = sin tope).")
        return n

    def configurar_sala(self, id_: str, precio: object | None = None,
                        nombre: object | None = None, activa: object | None = None,
                        tipo_juego: object | None = None, cupo_cartones: object | None = None,
                        max_cartones: object | None = None,
                        fecha_partida: object | None = None) -> Sala:
        """Cambia precio, nombre, tipo de juego, cupo o fecha de una sala de la casa.

        Es lo que usa el panel de administración, para no tener que tocar el
        repositorio cada vez que hay que cambiar algo de una sala.
        """
        sala = self.de(id_)
        # La sala de trabajo tiene dueño (la administración), pero se sigue
        # configurando desde aquí como cualquier sala de la casa.
        if sala.es_de_jugador and sala.id != SALA_CASA_ID:
            raise ErrorDeSalas("Las salas de jugador no se tocan desde aquí.")
        if sala.es_evento:
            raise ErrorDeSalas("La sala de eventos se configura aparte, con sus premios y aforo.")
        campos: dict = {}
        if precio is not None:
            campos["precio_carton"] = self._precio_valido(precio, PRECIO_MAXIMO_CASA, "de la sala")
        if nombre is not None:
            limpio = str(nombre).strip()
            if not limpio:
                raise ErrorDeSalas("Ponle un nombre a la sala.")
            if len(limpio) > NOMBRE_MAXIMO_CASA:
                raise ErrorDeSalas(f"El nombre de la sala no puede pasar de {NOMBRE_MAXIMO_CASA} letras.")
            campos["nombre"] = limpio
        if tipo_juego is not None:
            campos["tipo_juego"] = self._tipo_juego_valido(tipo_juego)
        if cupo_cartones is not None:
            campos["cupo_cartones"] = self._cupo_valido(cupo_cartones)
        if max_cartones is not None:
            campos["max_cartones"] = self._max_cartones_valido(max_cartones)
        if fecha_partida is not None:
            campos["fecha_partida"] = str(fecha_partida).strip()[:60]
        if activa is not None:
            campos["activa"] = int(bool(activa))
        if campos:
            self.almacen.actualizar_sala(sala.id, campos)
        return self.de(sala.id)

    def configurar_trabajo(self, id_: str, quien: str, precio: object | None = None,
                           tipo_juego: object | None = None,
                           fecha_partida: object | None = None) -> Sala:
        """El anfitrión pone el juego y el precio del cartón en SU sala de trabajo.

        Solo la puede ajustar su dueño. El precio se mueve dentro de los límites de
        las salas de jugador y el tipo de juego tiene que existir.
        """
        sala = self.de(id_)
        if not sala.es_de_jugador or sala.dueno != quien:
            raise ErrorDeSalas("Esa sala de trabajo no es tuya.")
        if not sala.es_trabajo:
            raise ErrorDeSalas("Esta sala no es una sala de trabajo.")
        campos: dict = {}
        if precio is not None:
            campos["precio_carton"] = self._precio_valido(precio, PRECIO_MAXIMO, "de tu sala")
        if tipo_juego is not None:
            campos["tipo_juego"] = self._tipo_juego_valido(tipo_juego)
        if fecha_partida is not None:
            campos["fecha_partida"] = str(fecha_partida).strip()[:60]
        if campos:
            self.almacen.actualizar_sala(sala.id, campos)
        return self.de(sala.id)

    def configurar_evento(self, precio: object | None = None, aforo: object | None = None,
                          premios_pct: object | None = None, activa: object | None = None,
                          nombre: object | None = None, tipo_juego: object | None = None,
                          cupo_cartones: object | None = None,
                          max_cartones: object | None = None,
                          fecha_partida: object | None = None) -> Sala:
        """Ajusta la sala de eventos: precio, aforo, premios, tipo de juego y fecha.

        Solo se cambia lo que se pasa. Los porcentajes son para 1º, 2º y 3º y no
        pueden sumar más de 100 %.
        """
        sala = self.evento()
        campos: dict = {}
        if precio is not None:
            campos["precio_carton"] = self._precio_valido(precio, PRECIO_MAXIMO_CASA,
                                                          "del evento")
        if nombre is not None:
            limpio = str(nombre).strip()
            if not limpio:
                raise ErrorDeSalas("Ponle un nombre a la sala.")
            if len(limpio) > NOMBRE_MAXIMO_CASA:
                raise ErrorDeSalas(f"El nombre de la sala no puede pasar de {NOMBRE_MAXIMO_CASA} letras.")
            campos["nombre"] = limpio
        if tipo_juego is not None:
            campos["tipo_juego"] = self._tipo_juego_valido(tipo_juego)
        if cupo_cartones is not None:
            campos["cupo_cartones"] = self._cupo_valido(cupo_cartones)
        if max_cartones is not None:
            campos["max_cartones"] = self._max_cartones_valido(max_cartones)
        if fecha_partida is not None:
            campos["fecha_partida"] = str(fecha_partida).strip()[:60]
        if aforo is not None:
            try:
                n = int(aforo)
            except (TypeError, ValueError):
                raise ErrorDeSalas("El aforo tiene que ser un número entero.") from None
            if n < 0 or n > AFORO_MAXIMO:
                raise ErrorDeSalas(f"El aforo tiene que estar entre 0 y {AFORO_MAXIMO} "
                                   "(0 = sin límite).")
            campos["aforo"] = n
        if premios_pct is not None:
            if isinstance(premios_pct, str):
                trozos = [t for t in premios_pct.replace(" ", "").split(",") if t]
            else:
                trozos = list(premios_pct)
            try:
                porcentajes = tuple(int(t) for t in trozos)
            except (TypeError, ValueError):
                raise ErrorDeSalas("Los porcentajes tienen que ser números enteros.") from None
            if not porcentajes or len(porcentajes) > PLAZAS_EVENTO:
                raise ErrorDeSalas(f"El evento reparte entre 1 y {PLAZAS_EVENTO} puestos.")
            if any(p < 0 or p > 100 for p in porcentajes):
                raise ErrorDeSalas("Cada porcentaje tiene que estar entre 0 y 100.")
            if sum(porcentajes) > 100:
                raise ErrorDeSalas("Los porcentajes no pueden sumar más de 100 %.")
            campos["premios_pct"] = ",".join(str(p) for p in porcentajes)
        if activa is not None:
            campos["activa"] = int(bool(activa))
        if campos:
            self.almacen.actualizar_sala(sala.id, campos)
        return self.evento()

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
            r = self.reparto_de_sala(fila["sala"], bote)
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
            "comision_pct": self.comision_de(correo),
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
            r = self._reparto_de_partida(fila)
            botes += r["bote"]
            premios += sum(r.get("premios", [r.get("premio", 0)]))
            comisiones += r.get("anfitrion", 0)
            app += r["app"]
            partidas += 1
        return {
            "partidas": partidas,
            "botes": botes, "botes_texto": a_texto(botes),
            "premios": premios, "premios_texto": a_texto(premios),
            "comisiones": comisiones, "comisiones_texto": a_texto(comisiones),
            "app": app, "app_texto": a_texto(app),
        }

    def economia_por_pais(self) -> dict:
        """La ganancia de la app (su parte) desglosada por país.

        Cada sala nace con un país, así que el dinero que deja una partida se
        imputa al país de su sala. Sirve para saber cuánto se cobra en cada
        cuenta de administración. Los importes se muestran en la moneda del país
        que corresponda, no en la del visitante.
        """
        por_pais: dict[str, dict] = {}
        for fila in self.almacen.partidas(1000):
            if fila["estado"] != "terminada":
                continue
            bote = fila["precio_carton"] * len(self.almacen.cartones(fila["id"]))
            if bote == 0:
                continue
            sala_fila = self.almacen.sala(fila["sala"]) if fila["sala"] else None
            claves = sala_fila.keys() if sala_fila is not None else ()
            code = (sala_fila["pais"] if "pais" in claves else "") or PAIS_POR_DEFECTO
            r = self._reparto_de_partida(fila)
            d = por_pais.setdefault(code, {"pais": code, "partidas": 0, "botes": 0,
                                           "premios": 0, "comisiones": 0, "app": 0})
            d["partidas"] += 1
            d["botes"] += r["bote"]
            d["premios"] += sum(r.get("premios", [r.get("premio", 0)]))
            d["comisiones"] += r.get("anfitrion", 0)
            d["app"] += r["app"]

        lista = []
        for code in sorted(por_pais):
            d = por_pais[code]
            d["botes_texto"] = formatear_local(d["botes"], code)
            d["premios_texto"] = formatear_local(d["premios"], code)
            d["comisiones_texto"] = formatear_local(d["comisiones"], code)
            d["app_texto"] = formatear_local(d["app"], code)
            d["cuenta_admin"] = cuenta_admin(code).a_dict()
            lista.append(d)
        return {"paises": lista, "app": sum(d["app"] for d in lista),
                "app_texto": a_texto(sum(d["app"] for d in lista))}

    def _reparto_de_partida(self, fila) -> dict:
        """Reparte el bote de una partida según el tipo de sala que la abrió."""
        bote = fila["precio_carton"] * len(self.almacen.cartones(fila["id"]))
        sala_fila = self.almacen.sala(fila["sala"]) if fila["sala"] else None
        if sala_fila is None:
            return reparto_del_bote(bote, con_anfitrion=False)
        return self.reparto_de_sala(fila["sala"], bote)

    def _es_de_jugador(self, sala_id: str) -> bool:
        fila = self.almacen.sala(sala_id)
        return bool(fila and fila["dueno"])

    def _a_sala(self, fila) -> Sala:
        claves = fila.keys()
        premios = ""
        if "premios_pct" in claves:
            premios = fila["premios_pct"] or ""
        return Sala(id=fila["id"], nombre=fila["nombre"], modo=fila["modo"],
                    precio_carton=fila["precio_carton"], dueno=fila["dueno"],
                    publica=bool(fila["publica"]), creada=fila["creada"],
                    activa=bool(fila["activa"]),
                    es_evento=bool(fila["es_evento"]) if "es_evento" in claves else False,
                    aforo=int(fila["aforo"]) if "aforo" in claves else 0,
                    premios_pct=tuple(int(p) for p in premios.split(",") if p),
                    tipo_juego=(fila["tipo_juego"] or TIPO_JUEGO_POR_DEFECTO)
                    if "tipo_juego" in claves else TIPO_JUEGO_POR_DEFECTO,
                    cupo_cartones=int(fila["cupo_cartones"]) if "cupo_cartones" in claves else 0,
                    max_cartones=int(fila["max_cartones"]) if "max_cartones" in claves else 0,
                    fecha_partida=(fila["fecha_partida"] or "") if "fecha_partida" in claves else "",
                    pais=(fila["pais"] or "VE") if "pais" in claves else "VE",
                    es_trabajo=bool(fila["es_trabajo"]) if "es_trabajo" in claves else False)
