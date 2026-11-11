"""Sala de bingo: partidas, jugadores, cartones y cantadas.

Una partida tiene cartones vendidos, un bombo y un patrón de premio. Se canta
"bingo" cuando un cartón completa el patrón. La sala comprueba la cantada contra
las bolas sacadas: no se fía de lo que diga el cliente.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field

from nucleo.money import a_centimos, multiplicar

from .cartones import (PATRONES, Bombo, Carton, ErrorDeBingo, generar_carton_unico,
                       huella_carton, patron_cumplido)


class ErrorDeSala(ValueError):
    """No se puede hacer esa jugada en la sala."""


@dataclass
class Partida:
    id: str
    patron: str
    precio_carton: int          # en céntimos
    sala: str = ""
    estado: str = "vendiendo"   # vendiendo | jugando | terminada
    cartones: dict[str, Carton] = field(default_factory=dict)   # id_carton -> carton
    dueno: dict[str, str] = field(default_factory=dict)         # id_carton -> jugador
    bombo: Bombo = field(default_factory=Bombo)
    ganador: str | None = None
    carton_ganador: str | None = None
    premio: int = 0
    empezada: float | None = None
    terminada: float | None = None
    plazas: int = 1             # cuántos ganadores acepta (3 en la sala de eventos)
    ganadores: list[dict] = field(default_factory=list)  # en orden: 1º, 2º, 3º

    @property
    def abierta(self) -> bool:
        return self.estado == "vendiendo"

    @property
    def completa(self) -> bool:
        """¿Ya se han cantado todos los puestos premiados?"""
        return len(self.ganadores) >= self.plazas

    def jugadores(self) -> list[str]:
        """Correos distintos que tienen cartón en esta partida."""
        vistos: list[str] = []
        for correo in self.dueno.values():
            if correo not in vistos:
                vistos.append(correo)
        return vistos

    def cartones_de(self, jugador: str) -> list[str]:
        return [c for c, d in self.dueno.items() if d == jugador]


class Sala:
    """Gestiona partidas. No mueve dinero: devuelve órdenes para el monedero."""

    def __init__(self, patron_por_defecto: str = "linea_h1") -> None:
        self.partidas: dict[str, Partida] = {}
        self.patron_por_defecto = patron_por_defecto

    # -- partidas --

    def abrir_partida(
        self, precio_carton: object, patron: str | None = None, id_: str | None = None,
        sala: str = "", plazas: int = 1,
    ) -> Partida:
        patron = patron or self.patron_por_defecto
        if patron not in PATRONES:
            raise ErrorDeSala(f"No existe el patrón {patron!r}.")
        precio = a_centimos(precio_carton)
        if precio <= 0:
            raise ErrorDeSala("El precio del cartón tiene que ser mayor que cero.")
        if plazas < 1:
            raise ErrorDeSala("Una partida necesita al menos un puesto premiado.")
        pid = id_ or f"p-{secrets.token_hex(4)}"
        if pid in self.partidas:
            raise ErrorDeSala(f"La partida {pid} ya existe.")
        partida = Partida(id=pid, patron=patron, precio_carton=precio, sala=sala, plazas=plazas)
        self.partidas[pid] = partida
        return partida

    def comprar_carton(self, partida_id: str, jugador: str) -> tuple[Carton, int]:
        """Vende un cartón. Devuelve el cartón y lo que hay que cobrar (céntimos).

        Quien llama (la mesa) es responsable de cobrar ese importe. Si no se cobra,
        el cartón queda vendido igual: por eso la mesa cobra antes de llamar aquí.
        """
        partida = self._partida(partida_id)
        if not partida.abierta:
            raise ErrorDeSala("La partida ya ha empezado: no se venden más cartones.")
        usados = {huella_carton(c) for c in partida.cartones.values()}
        carton = generar_carton_unico(id_="", usados=usados)
        partida.cartones[carton.id] = carton
        partida.dueno[carton.id] = jugador
        return carton, partida.precio_carton

    def empezar(self, partida_id: str) -> Partida:
        partida = self._partida(partida_id)
        if not partida.abierta:
            raise ErrorDeSala(f"La partida no está en venta ({partida.estado}).")
        if not partida.cartones:
            raise ErrorDeSala("No se puede empezar una partida sin cartones vendidos.")
        partida.estado = "jugando"
        partida.empezada = time.time()
        return partida

    # -- juego --

    def sacar_bola(self, partida_id: str) -> int:
        """Saca una bola y la marca en todos los cartones. Devuelve el número."""
        partida = self._partida(partida_id)
        if partida.estado != "jugando":
            raise ErrorDeSala("La partida no está en juego.")
        bola = partida.bombo.sacar()
        for carton in partida.cartones.values():
            carton.marcar(bola)
        return bola

    def cantar(self, partida_id: str, jugador: str, carton_id: str) -> dict:
        """Comprueba una cantada de bingo contra las bolas ya sacadas.

        No se fía de nadie: solo es válida si el cartón pertenece a ese jugador y
        tiene el patrón realmente completo. En una partida de un solo puesto, el
        que canta cierra la partida; en la de eventos, cada cantada válida ocupa
        el siguiente puesto (1º, 2º, 3º) y un jugador no puede repetir puesto.
        """
        partida = self._partida(partida_id)
        if partida.estado != "jugando":
            raise ErrorDeSala("No se puede cantar bingo en esta partida.")
        if partida.completa:
            raise ErrorDeSala("Ya están cubiertos todos los puestos de esta partida.")
        carton = partida.cartones.get(carton_id)
        if carton is None:
            raise ErrorDeSala(f"El cartón {carton_id!r} no está en esta partida.")
        if partida.dueno[carton_id] != jugador:
            raise ErrorDeSala("Ese cartón no es tuyo.")
        if any(g["correo"] == jugador for g in partida.ganadores):
            raise ErrorDeSala("Ya te llevaste un puesto en esta partida.")
        if not patron_cumplido(carton, partida.patron):
            raise ErrorDeSala("Bingo cantado en falso: al cartón le falta el patrón.")

        puesto = len(partida.ganadores) + 1
        partida.ganadores.append({
            "puesto": puesto, "correo": jugador, "carton": carton_id,
            "bolas": len(partida.bombo.sacadas),
        })
        # El primer ganador queda también como ganador principal (compatibilidad).
        if partida.ganador is None:
            partida.ganador = jugador
            partida.carton_ganador = carton_id
        if partida.completa:
            partida.estado = "terminada"
            partida.terminada = time.time()
        return {
            "partida": partida_id,
            "ganador": jugador,
            "carton": carton_id,
            "puesto": puesto,
            "plazas": partida.plazas,
            "ganadores": list(partida.ganadores),
            "bolas": len(partida.bombo.sacadas),
        }

    def cerrar_a_mano(self, partida_id: str) -> Partida:
        """Cierra una partida sin ganador (se acabaron las bolas o se cancela)."""
        partida = self._partida(partida_id)
        if partida.estado == "terminada":
            raise ErrorDeSala("La partida ya está terminada.")
        partida.estado = "terminada"
        partida.terminada = time.time()
        return partida

    def bote(self, partida_id: str) -> int:
        """Lo que se recaudó con los cartones de esta partida (céntimos)."""
        partida = self._partida(partida_id)
        return partida.precio_carton * len(partida.cartones)

    def _partida(self, partida_id: str) -> Partida:
        try:
            return self.partidas[partida_id]
        except KeyError:
            raise ErrorDeSala(f"No existe la partida {partida_id!r}.") from None
