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
# Las salas de la casa y el evento los pone la administración desde el panel, así
# que su tope es más alto que el de las salas de jugador.
PRECIO_MINIMO = 1_00        # Bs 1,00
PRECIO_MAXIMO = 500_00      # Bs 500,00 (salas de jugador)
PRECIO_MAXIMO_CASA = 100_000_00  # Bs 100.000,00 (salas de la casa y el evento)

MODOS_VALIDOS = ("normal", "carton_lleno", "competencia")

# Tipos de juego (patrón que premia la sala). Los pone la administración.
TIPO_JUEGO_POR_DEFECTO = "linea_h1"
CUPO_MAXIMO_CARTONES = 1000        # cartones que se pueden vender en una sala (0 = sin tope)

# Las salas de la casa llevan nombre de estado de Venezuela. El último dato es
# el tipo de juego que premia la sala.
SALAS_INICIALES = (
    ("sala-zulia", "Zulia", "normal", 2_000_00, "linea_h1"),
    ("sala-lara", "Lara", "competencia", 1_000_00, "cuatro_esquinas"),
    ("sala-carabobo", "Carabobo", "carton_lleno", 500_00, "carton_lleno"),
    ("sala-miranda", "Mérida", "normal", 200_00, "cruz_grande"),
    ("sala-tachira", "Táchira", "competencia", 100_00, "cruz_pequena"),
    ("sala-nueva-esparta", "Nueva Esparta", "carton_lleno", 50_00, "diagonal"),
)

# Precios que traían las salas antes de que la administración pudiera cambiarlos.
# Se usan una sola vez, para subir la base de datos de quien ya tenía el programa
# funcionando. Si un precio no coincide con el viejo, es que lo cambió el admin y
# no se toca.
SALAS_INICIALES_ANTIGUAS = {
    "sala-zulia": 5_00,
    "sala-lara": 10_00,
    "sala-carabobo": 20_00,
    "sala-miranda": 50_00,
    "sala-tachira": 100_00,
    "sala-nueva-esparta": 200_00,
}

# Nombre viejo de la sala de Mérida, cuando era "Miranda".
NOMBRE_VIEJO_MIRANDA = "Miranda"

# Marca de "los precios nuevos ya se aplicaron". Sube solo si hay que volver a
# tocar los precios de las bases ya existentes.
VERSION_PRECIOS = 1

# Sala de eventos: la maneja la administración. Ella pone el aforo, el precio del
# cartón y el porcentaje del bote que se lleva cada puesto.
SALA_EVENTO_ID = "sala-evento-lago"
SALA_EVENTO_NOMBRE = "Sala de Eventos Lago de Maracaibo"
SALA_EVENTO_MODO = "competencia"
SALA_EVENTO_TIPO = "cruz_grande"           # tipo de juego por defecto del evento
SALA_EVENTO_PRECIO = 50_00                 # Bs 50,00 por cartón
SALA_EVENTO_AFORO = 50                     # jugadores como máximo (0 = sin límite)
SALA_EVENTO_CUPO = 0                       # cartones como máximo (0 = sin tope)
PREMIO_EVENTO_POR_DEFECTO = (60, 15, 5)    # % del bote para 1º, 2º y 3º
PLAZAS_EVENTO = len(PREMIO_EVENTO_POR_DEFECTO)
AFORO_MAXIMO = 1000

NOMBRES_RESERVADOS = tuple(n.lower() for _, n, _, _, _ in SALAS_INICIALES) + (
    NOMBRE_VIEJO_MIRANDA.lower(), SALA_EVENTO_NOMBRE.lower(), "lago de maracaibo",
)


def reparto_del_bote(bote: int, con_anfitrion: bool, comision_pct: int | None = None) -> dict:
    """Parte el bote en premio, comisión del anfitrión y lo que queda a la app.

    El resto del redondeo se le da al ganador, nunca a la casa: si sobra un
    céntimo, es del jugador. Así la app nunca gana por un error de redondeo.
    La comisión del anfitrión se puede ajustar por cuenta (comision_pct, en %);
    si no se pasa, se usa la de por defecto.
    """
    if not isinstance(bote, int) or bote < 0:
        raise ErrorDeSalas(f"El bote tiene que ser un entero de céntimos, no {bote!r}.")

    pct = int(COMISION_ANFITRION * 100) if comision_pct is None else comision_pct
    if not isinstance(pct, int) or isinstance(pct, bool) or not 0 <= pct <= 100:
        raise ErrorDeSalas(f"Porcentaje de anfitrión no válido: {pct!r}.")

    proporcion = PREMIO_CON_ANFITRION if con_anfitrion else PREMIO_CASA
    premio = int((Decimal(bote) * proporcion).quantize(Decimal("1")))
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


def reparto_evento(bote: int, porcentajes: tuple[int, ...] | list[int]) -> dict:
    """Parte el bote de un evento entre los puestos, por porcentaje.

    Cada puesto cobra su porcentaje del bote, truncado al céntimo. Lo que no se
    reparte queda para la app, así que la suma de los premios más lo de la app es
    exactamente el bote.
    """
    if not isinstance(bote, int) or bote < 0:
        raise ErrorDeSalas(f"El bote tiene que ser un entero de céntimos, no {bote!r}.")
    if not porcentajes:
        raise ErrorDeSalas("Un evento necesita al menos un puesto premiado.")
    for pct in porcentajes:
        if not isinstance(pct, int) or isinstance(pct, bool) or pct < 0:
            raise ErrorDeSalas(f"Porcentaje no válido: {pct!r}.")
    if sum(porcentajes) > 100:
        raise ErrorDeSalas("Los porcentajes no pueden sumar más de 100 %.")
    premios = [bote * pct // 100 for pct in porcentajes]
    return {"bote": bote, "premios": premios, "app": bote - sum(premios),
            "porcentajes": list(porcentajes)}


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
    fecha_partida: str = ""            # cuándo se juega (texto libre: "hoy 8 pm")

    @property
    def es_de_jugador(self) -> bool:
        return bool(self.dueno)

    @property
    def nombre_tipo_juego(self) -> str:
        from bingo.cartones import NOMBRE_TIPO_JUEGO
        return NOMBRE_TIPO_JUEGO.get(self.tipo_juego, self.tipo_juego)

    @property
    def comision_anfitrion(self) -> int:
        """Céntimos que cobra el anfitrión por cada 100 de bote."""
        return int(COMISION_ANFITRION * 100) if self.es_de_jugador else 0

    @property
    def plazas(self) -> int:
        """Cuántos puestos premiados reparte el evento."""
        return len(self.premios_pct)

    def reparto(self, bote: int, comision_pct: int | None = None) -> dict:
        if self.es_evento:
            return reparto_evento(bote, self.premios_pct)
        return reparto_del_bote(bote, con_anfitrion=self.es_de_jugador, comision_pct=comision_pct)

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
            "es_evento": self.es_evento,
            "aforo": self.aforo,
            "premios_pct": list(self.premios_pct),
            "tipo_juego": self.tipo_juego,
            "tipo_juego_texto": self.nombre_tipo_juego,
            "cupo_cartones": self.cupo_cartones,
            "fecha_partida": self.fecha_partida,
        }


class Salas:
    """Gestiona las salas: las de la casa y las que crean los jugadores."""

    def __init__(self, almacen, usuarios=None) -> None:
        self.almacen = almacen
        self.usuarios = usuarios
        self._asegurar_iniciales()
        self._subir_precios_antiguos()

    def comision_de(self, dueno: str) -> int:
        """El % de comisión de anfitrión que le toca a una cuenta.

        Cada cuenta puede tener su propio porcentaje (lo pone la administración);
        si no lo tiene, se usa el de por defecto.
        """
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
        nuevos = {id_: precio for id_, _, _, precio, _ in SALAS_INICIALES}
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
        self.almacen.guardar_meta("precios_v", str(VERSION_PRECIOS))

    def _asegurar_iniciales(self) -> None:
        """Crea las salas de la casa la primera vez. No pisa las que ya existan."""
        for id_, nombre, modo, precio, tipo in SALAS_INICIALES:
            if self.almacen.sala(id_) is None:
                self.almacen.guardar_sala({
                    "id": id_, "nombre": nombre, "modo": modo, "precio_carton": precio,
                    "dueno": "", "publica": 1, "creada": time.time(), "activa": 1,
                    "es_evento": 0, "aforo": 0, "premios_pct": "", "tipo_juego": tipo,
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
        """Las salas de los estados, sin la de eventos."""
        return [s for s in self.todas(incluir_inactivas) if not s.es_evento and not s.dueno]

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
        centimos = self._precio_valido(precio, PRECIO_MAXIMO, "de tu sala")
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

    def comision_de_sala(self, sala_id: str) -> int:
        """El % de comisión que cobra el anfitrión de una sala (0 si no tiene dueño)."""
        fila = self.almacen.sala(sala_id)
        if not fila or not fila["dueno"]:
            return 0
        return self.comision_de(fila["dueno"])

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

    def configurar_sala(self, id_: str, precio: object | None = None,
                        nombre: object | None = None, activa: object | None = None,
                        tipo_juego: object | None = None, cupo_cartones: object | None = None,
                        fecha_partida: object | None = None) -> Sala:
        """Cambia precio, nombre, tipo de juego, cupo o fecha de una sala de la casa.

        Es lo que usa el panel de administración, para no tener que tocar el
        repositorio cada vez que hay que cambiar algo de una sala.
        """
        sala = self.de(id_)
        if sala.es_de_jugador:
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
            if len(limpio) > 30:
                raise ErrorDeSalas("El nombre de la sala no puede pasar de 30 letras.")
            campos["nombre"] = limpio
        if tipo_juego is not None:
            campos["tipo_juego"] = self._tipo_juego_valido(tipo_juego)
        if cupo_cartones is not None:
            campos["cupo_cartones"] = self._cupo_valido(cupo_cartones)
        if fecha_partida is not None:
            campos["fecha_partida"] = str(fecha_partida).strip()[:60]
        if activa is not None:
            campos["activa"] = int(bool(activa))
        if campos:
            self.almacen.actualizar_sala(sala.id, campos)
        return self.de(sala.id)

    def configurar_evento(self, precio: object | None = None, aforo: object | None = None,
                          premios_pct: object | None = None, activa: object | None = None,
                          nombre: object | None = None, tipo_juego: object | None = None,
                          cupo_cartones: object | None = None,
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
            if len(limpio) > 40:
                raise ErrorDeSalas("El nombre de la sala no puede pasar de 40 letras.")
            campos["nombre"] = limpio
        if tipo_juego is not None:
            campos["tipo_juego"] = self._tipo_juego_valido(tipo_juego)
        if cupo_cartones is not None:
            campos["cupo_cartones"] = self._cupo_valido(cupo_cartones)
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
            r = reparto_del_bote(bote, con_anfitrion=True, comision_pct=self.comision_de(correo))
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

    def _reparto_de_partida(self, fila) -> dict:
        """Reparte el bote de una partida según el tipo de sala que la abrió."""
        bote = fila["precio_carton"] * len(self.almacen.cartones(fila["id"]))
        sala_fila = self.almacen.sala(fila["sala"]) if fila["sala"] else None
        if sala_fila and sala_fila["es_evento"]:
            premios = tuple(int(p) for p in (sala_fila["premios_pct"] or "").split(",") if p)
            return reparto_evento(bote, premios)
        con_anf = bool(sala_fila and sala_fila["dueno"])
        comision = self.comision_de(sala_fila["dueno"]) if con_anf else None
        return reparto_del_bote(bote, con_anfitrion=con_anf, comision_pct=comision)

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
                    fecha_partida=(fila["fecha_partida"] or "") if "fecha_partida" in claves else "")
